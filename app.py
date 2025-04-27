import os
import logging
import secrets
from PIL import Image
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, redirect, url_for, request, flash, abort, current_app
from flask_login import LoginManager, current_user, login_user, logout_user, login_required
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from functools import wraps

from config import config
from models import db, User, ContactMessage, ForumCategory, ForumTopic, ForumPost, Campaign, Donation
from models import Post, Comment, Like, followers, Livestream, LivestreamComment
from forms import LoginForm, RegistrationForm, ContactForm, CampaignForm, DonationForm
from forms import ForumTopicForm, ForumPostForm, CategoryForm, ProfileForm, PostForm, CommentForm, SearchForm
from forms import LivestreamForm, LivestreamCommentForm

def create_app(config_name='default'):
    """Application factory function"""
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)

    # Setup login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message_category = 'info'

    # Ensure upload directories exist
    with app.app_context():
        os.makedirs(os.path.join(app.static_folder, 'uploads', 'profile_pics'), exist_ok=True)
        os.makedirs(os.path.join(app.static_folder, 'uploads', 'posts'), exist_ok=True)
        os.makedirs(os.path.join(app.static_folder, 'uploads', 'thumbnails'), exist_ok=True)
        os.makedirs(os.path.join(app.static_folder, 'hls'), exist_ok=True)

    # Utility functions for file uploads
    def save_profile_picture(form_picture):
        """Save profile picture with a unique filename and resize it"""
        random_hex = secrets.token_hex(8)
        _, f_ext = os.path.splitext(form_picture.filename)
        picture_fn = random_hex + f_ext
        picture_path = os.path.join(app.static_folder, 'uploads', 'profile_pics', picture_fn)

        # Resize image to save space and load faster
        output_size = (150, 150)
        i = Image.open(form_picture)
        i.thumbnail(output_size)
        i.save(picture_path)

        return picture_fn

    def save_post_image(form_picture):
        """Save post image with a unique filename"""
        random_hex = secrets.token_hex(8)
        _, f_ext = os.path.splitext(form_picture.filename)
        picture_fn = random_hex + f_ext
        picture_path = os.path.join(app.static_folder, 'uploads', 'posts', picture_fn)

        # Save the image, resize if needed
        output_size = (1200, 1200)  # Maximum dimension while maintaining aspect ratio
        i = Image.open(form_picture)
        i.thumbnail(output_size, Image.LANCZOS)
        i.save(picture_path)

        return picture_fn

    # Admin required decorator
    def admin_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_admin:
                flash('You must be an administrator to access this page.', 'danger')
                return redirect(url_for('home'))
            return f(*args, **kwargs)
        return decorated_function

    # Admin routes
    @app.route('/admin')
    @login_required
    @admin_required
    def admin_dashboard():
        # Collect statistics for dashboard
        stats = {
            'users': User.query.count(),
            'messages': ContactMessage.query.count(),
            'unread_messages': ContactMessage.query.filter_by(is_read=False).count(),
            'categories': ForumCategory.query.count(),
            'topics': ForumTopic.query.count(),
            'campaigns': Campaign.query.count(),
            'active_campaigns': Campaign.query.filter(Campaign.end_date > datetime.utcnow()).count(),
            'donations_count': Donation.query.count(),
            'donations_total': db.session.query(db.func.sum(Donation.amount)).scalar() or 0
        }

        # Get recent activity
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        recent_topics = ForumTopic.query.order_by(ForumTopic.created_at.desc()).limit(5).all()

        return render_template('admin/dashboard.html', stats=stats, 
                              recent_users=recent_users, 
                              recent_topics=recent_topics)

    @app.route('/admin/users')
    @login_required
    @admin_required
    def admin_users():
        page = request.args.get('page', 1, type=int)
        search = request.args.get('search', '')
        filter_type = request.args.get('filter', 'all')

        query = User.query

        # Apply filters
        if search:
            query = query.filter(db.or_(
                User.username.contains(search),
                User.email.contains(search)
            ))

        if filter_type == 'admin':
            query = query.filter_by(is_admin=True)
        elif filter_type == 'regular':
            query = query.filter_by(is_admin=False)

        # Paginate results
        pagination = query.order_by(User.created_at.desc()).paginate(
            page=page, per_page=15, error_out=False)
        users = pagination.items

        return render_template('admin/users.html', users=users, pagination=pagination)

    @app.route('/admin/users/<int:user_id>/toggle-admin', methods=['POST'])
    @login_required
    @admin_required
    def toggle_admin_status(user_id):
        user = User.query.get_or_404(user_id)

        # Prevent changing the original admin (ID 1)
        if user.id == 1 and current_user.id != 1:
            flash('You cannot modify the status of the superadmin.', 'danger')
            return redirect(url_for('admin_users'))

        user.is_admin = not user.is_admin
        db.session.commit()

        action = 'added to' if user.is_admin else 'removed from'
        flash(f'{user.username} has been {action} administrators.', 'success')
        return redirect(url_for('admin_users'))

    @app.route('/admin/users/<int:user_id>/toggle-status', methods=['POST'])
    @login_required
    @admin_required
    def toggle_user_status(user_id):
        user = User.query.get_or_404(user_id)

        # Prevent deactivating the original admin (ID 1)
        if user.id == 1:
            flash('You cannot deactivate the superadmin.', 'danger')
            return redirect(url_for('admin_users'))

        # Don't allow deactivating yourself
        if user.id == current_user.id:
            flash('You cannot deactivate your own account.', 'danger')
            return redirect(url_for('admin_users'))

        user.is_active = not user.is_active
        db.session.commit()

        status = 'activated' if user.is_active else 'deactivated'
        flash(f'{user.username} has been {status}.', 'success')
        return redirect(url_for('admin_users'))

    @app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
    @login_required
    @admin_required
    def delete_user(user_id):
        user = User.query.get_or_404(user_id)

        # Prevent deleting the original admin (ID 1)
        if user.id == 1:
            flash('You cannot delete the superadmin.', 'danger')
            return redirect(url_for('admin_users'))

        # Don't allow deleting yourself
        if user.id == current_user.id:
            flash('You cannot delete your own account.', 'danger')
            return redirect(url_for('admin_users'))

        username = user.username
        db.session.delete(user)
        db.session.commit()

        flash(f'User {username} has been deleted.', 'success')
        return redirect(url_for('admin_users'))

    @app.route('/admin/categories', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def admin_categories():
        form = CategoryForm()
        if form.validate_on_submit():
            category = ForumCategory(
                name=form.name.data,
                description=form.description.data
            )
            db.session.add(category)
            db.session.commit()
            flash('New category has been created.', 'success')
            return redirect(url_for('admin_categories'))

        categories = ForumCategory.query.all()
        return render_template('admin/categories.html', categories=categories, form=form)

    @app.route('/admin/categories/<int:category_id>/edit', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def edit_category(category_id):
        category = ForumCategory.query.get_or_404(category_id)
        form = CategoryForm(obj=category)

        if form.validate_on_submit():
            category.name = form.name.data
            category.description = form.description.data
            db.session.commit()
            flash('Category has been updated.', 'success')
            return redirect(url_for('admin_categories'))

        return render_template('admin/edit_category.html', form=form, category=category)

    @app.route('/admin/categories/<int:category_id>/delete', methods=['POST'])
    @login_required
    @admin_required
    def delete_category(category_id):
        category = ForumCategory.query.get_or_404(category_id)

        # Make sure there are no topics in this category
        if category.topics.count() > 0:
            flash('Cannot delete a category that contains topics.', 'danger')
            return redirect(url_for('admin_categories'))

        name = category.name
        db.session.delete(category)
        db.session.commit()

        flash(f'Category "{name}" has been deleted.', 'success')
        return redirect(url_for('admin_categories'))

    @app.route('/admin/topics')
    @login_required
    @admin_required
    def admin_topics():
        page = request.args.get('page', 1, type=int)
        search = request.args.get('search', '')
        category_id = request.args.get('category', 'all')

        query = ForumTopic.query

        # Apply filters
        if search:
            query = query.filter(ForumTopic.title.contains(search))

        if category_id != 'all':
            query = query.filter_by(category_id=int(category_id))

        # Paginate results
        pagination = query.order_by(ForumTopic.created_at.desc()).paginate(
            page=page, per_page=15, error_out=False)
        topics = pagination.items

        categories = ForumCategory.query.all()

        return render_template('admin/topics.html', topics=topics, 
                              categories=categories, pagination=pagination)

    @app.route('/admin/topics/<int:topic_id>/pin', methods=['POST'])
    @login_required
    @admin_required
    def pin_topic(topic_id):
        topic = ForumTopic.query.get_or_404(topic_id)
        topic.is_pinned = not topic.is_pinned
        db.session.commit()

        action = 'pinned' if topic.is_pinned else 'unpinned'
        flash(f'Topic has been {action}.', 'success')
        return redirect(url_for('admin_topics'))

    @app.route('/admin/topics/<int:topic_id>/lock', methods=['POST'])
    @login_required
    @admin_required
    def lock_topic(topic_id):
        topic = ForumTopic.query.get_or_404(topic_id)
        topic.is_locked = not topic.is_locked
        db.session.commit()

        action = 'locked' if topic.is_locked else 'unlocked'
        flash(f'Topic has been {action}.', 'success')
        return redirect(url_for('admin_topics'))

    @app.route('/admin/topics/<int:topic_id>/move', methods=['POST'])
    @login_required
    @admin_required
    def move_topic(topic_id):
        topic = ForumTopic.query.get_or_404(topic_id)
        new_category_id = request.form.get('category_id', type=int)

        if not new_category_id:
            flash('Please select a valid category.', 'danger')
            return redirect(url_for('admin_topics'))

        category = ForumCategory.query.get_or_404(new_category_id)
        topic.category_id = new_category_id
        db.session.commit()

        flash(f'Topic has been moved to {category.name}.', 'success')
        return redirect(url_for('admin_topics'))

    @app.route('/admin/topics/<int:topic_id>/delete', methods=['POST'])
    @login_required
    @admin_required
    def delete_topic(topic_id):
        topic = ForumTopic.query.get_or_404(topic_id)
        title = topic.title

        # Delete all posts in the topic first
        ForumPost.query.filter_by(topic_id=topic.id).delete()

        db.session.delete(topic)
        db.session.commit()

        flash(f'Topic "{title}" and all its posts have been deleted.', 'success')
        return redirect(url_for('admin_topics'))

    @app.route('/admin/campaigns')
    @login_required
    @admin_required
    def admin_campaigns():
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')

        query = Campaign.query
        now = datetime.utcnow()

        # Apply filters
        if status == 'active':
            query = query.filter(Campaign.end_date > now, Campaign.is_approved == True)
        elif status == 'ended':
            query = query.filter(Campaign.end_date <= now)
        elif status == 'pending':
            query = query.filter(Campaign.is_approved == False)

        # Paginate results
        pagination = query.order_by(Campaign.created_at.desc()).paginate(
            page=page, per_page=10, error_out=False)
        campaigns = pagination.items

        return render_template('admin/campaigns.html', campaigns=campaigns, 
                              pagination=pagination, now=now)

    @app.route('/admin/campaigns/<int:campaign_id>/approve', methods=['POST'])
    @login_required
    @admin_required
    def approve_campaign(campaign_id):
        campaign = Campaign.query.get_or_404(campaign_id)
        campaign.is_approved = True
        db.session.commit()

        flash(f'Campaign "{campaign.title}" has been approved.', 'success')
        return redirect(url_for('admin_campaigns'))

    @app.route('/admin/campaigns/<int:campaign_id>/feature', methods=['POST'])
    @login_required
    @admin_required
    def feature_campaign(campaign_id):
        campaign = Campaign.query.get_or_404(campaign_id)
        campaign.is_featured = not campaign.is_featured
        db.session.commit()

        action = 'featured' if campaign.is_featured else 'unfeatured'
        flash(f'Campaign "{campaign.title}" has been {action}.', 'success')
        return redirect(url_for('admin_campaigns'))

    @app.route('/admin/campaigns/<int:campaign_id>/edit', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def edit_campaign(campaign_id):
        campaign = Campaign.query.get_or_404(campaign_id)
        form = CampaignForm(obj=campaign)

        if form.validate_on_submit():
            campaign.title = form.title.data
            campaign.description = form.description.data
            campaign.goal_amount = form.goal_amount.data
            campaign.end_date = form.end_date.data
            db.session.commit()

            flash(f'Campaign "{campaign.title}" has been updated.', 'success')
            return redirect(url_for('admin_campaigns'))

        return render_template('admin/edit_campaign.html', form=form, campaign=campaign)

    @app.route('/admin/campaigns/<int:campaign_id>/delete', methods=['POST'])
    @login_required
    @admin_required
    def delete_campaign(campaign_id):
        campaign = Campaign.query.get_or_404(campaign_id)
        title = campaign.title

        # Delete all donations to this campaign first
        Donation.query.filter_by(campaign_id=campaign.id).delete()

        db.session.delete(campaign)
        db.session.commit()

        flash(f'Campaign "{title}" and all its donations have been deleted.', 'success')
        return redirect(url_for('admin_campaigns'))

    @app.route('/admin/messages')
    @login_required
    @admin_required
    def admin_messages():
        messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
        return render_template('admin/messages.html', messages=messages)

    @app.route('/admin/messages/<int:message_id>/mark-read', methods=['POST'])
    @login_required
    @admin_required
    def mark_message_read(message_id):
        message = ContactMessage.query.get_or_404(message_id)
        message.is_read = True
        db.session.commit()

        flash('Message marked as read.', 'success')
        return redirect(url_for('admin_messages'))

    @app.route('/admin/messages/<int:message_id>/delete', methods=['POST'])
    @login_required
    @admin_required
    def delete_message(message_id):
        message = ContactMessage.query.get_or_404(message_id)
        db.session.delete(message)
        db.session.commit()

        flash('Message deleted.', 'success')
        return redirect(url_for('admin_messages'))

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints (if you have them)
    # from auth import bp as auth_bp
    # app.register_blueprint(auth_bp)

    # Setup logging for production
    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        file_handler = RotatingFileHandler('logs/growhaven.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('GrowHaven startup')

    # Routes for different pages
    @app.route('/')
    def home():
        campaigns = Campaign.query.filter(Campaign.end_date > datetime.utcnow()).order_by(Campaign.start_date.desc()).limit(3).all()
        return render_template('home.html', campaigns=campaigns)

    @app.route('/about')
    def about():
        return render_template('about.html')

    @app.route('/contact', methods=['GET', 'POST'])
    def contact():
        form = ContactForm()
        if form.validate_on_submit():
            message = ContactMessage(
                name=form.name.data,
                email=form.email.data,
                subject=form.subject.data,
                message=form.message.data
            )
            db.session.add(message)
            db.session.commit()

            # In a production app, you would send an email notification here

            flash('Thank you for your message! We\'ll get back to you soon.', 'success')
            return redirect(url_for('contact'))

        return render_template('contact.html', form=form)

    @app.route('/forum')
    def forum():
        categories = ForumCategory.query.all()
        recent_topics = ForumTopic.query.order_by(ForumTopic.created_at.desc()).limit(5).all()
        return render_template('forum.html', categories=categories, recent_topics=recent_topics)

    @app.route('/forum/category/<int:category_id>')
    def forum_category(category_id):
        category = ForumCategory.query.get_or_404(category_id)
        topics = category.topics.order_by(ForumTopic.created_at.desc()).all()
        return render_template('forum_category.html', category=category, topics=topics)

    @app.route('/forum/topic/<int:topic_id>', methods=['GET', 'POST'])
    def forum_topic(topic_id):
        topic = ForumTopic.query.get_or_404(topic_id)
        form = ForumPostForm()

        if form.validate_on_submit():
            if not current_user.is_authenticated:
                flash('You need to be logged in to post replies.', 'danger')
                return redirect(url_for('login', next=request.url))

            post = ForumPost(
                content=form.content.data,
                user_id=current_user.id,
                topic_id=topic.id
            )
            db.session.add(post)
            db.session.commit()
            flash('Your reply has been posted!', 'success')
            return redirect(url_for('forum_topic', topic_id=topic.id))

        posts = topic.posts.order_by(ForumPost.created_at).all()
        return render_template('forum_topic.html', topic=topic, posts=posts, form=form)

    @app.route('/forum/new_topic/<int:category_id>', methods=['GET', 'POST'])
    @login_required
    def new_topic(category_id):
        category = ForumCategory.query.get_or_404(category_id)
        form = ForumTopicForm()

        if form.validate_on_submit():
            topic = ForumTopic(
                title=form.title.data,
                content=form.content.data,
                user_id=current_user.id,
                category_id=category.id
            )
            db.session.add(topic)
            db.session.commit()
            flash('Your topic has been created!', 'success')
            return redirect(url_for('forum_topic', topic_id=topic.id))

        return render_template('new_topic.html', form=form, category=category)

    @app.route('/fundraising')
    def fundraising():
        active_campaigns = Campaign.query.filter(Campaign.end_date > datetime.utcnow()).all()
        return render_template('fundraising.html', campaigns=active_campaigns)

    @app.route('/fundraising/campaign/<int:campaign_id>', methods=['GET', 'POST'])
    def campaign(campaign_id):
        campaign = Campaign.query.get_or_404(campaign_id)
        form = DonationForm()

        if form.validate_on_submit():
            if not current_user.is_authenticated:
                flash('You need to be logged in to make a donation.', 'danger')
                return redirect(url_for('login', next=request.url))

            donation = Donation(
                amount=form.amount.data,
                message=form.message.data,
                is_anonymous=form.is_anonymous.data,
                user_id=current_user.id,
                campaign_id=campaign.id
            )

            # Update campaign amount
            campaign.current_amount += form.amount.data

            db.session.add(donation)
            db.session.commit()

            flash('Thank you for your donation!', 'success')
            return redirect(url_for('campaign', campaign_id=campaign.id))

        # Get recent donations
        donations = Donation.query.filter_by(campaign_id=campaign.id).order_by(Donation.created_at.desc()).limit(10).all()
        return render_template('campaign.html', campaign=campaign, donations=donations, form=form)

    @app.route('/fundraising/new_campaign', methods=['GET', 'POST'])
    @login_required
    def new_campaign():
        form = CampaignForm()

        if form.validate_on_submit():
            # Make sure end date is in the future
            if form.end_date.data <= datetime.utcnow().date():
                flash('End date must be in the future.', 'danger')
                return render_template('new_campaign.html', form=form)

            campaign = Campaign(
                title=form.title.data,
                description=form.description.data,
                goal_amount=form.goal_amount.data,
                end_date=form.end_date.data,
                user_id=current_user.id
            )
            db.session.add(campaign)
            db.session.commit()

            flash('Your campaign has been created!', 'success')
            return redirect(url_for('campaign', campaign_id=campaign.id))

        return render_template('new_campaign.html', form=form)

    # Social Media Routes
    @app.route('/feed')
    @login_required
    def feed():
        page = request.args.get('page', 1, type=int)

        # Get posts from followed users + own posts
        followed_posts = current_user.followed_posts()
        own_posts = Post.query.filter_by(user_id=current_user.id)
        all_posts = followed_posts.union(own_posts).order_by(Post.created_at.desc())

        # Paginate posts
        posts = all_posts.paginate(page=page, per_page=10, error_out=False)

        # Get suggested users (users you don't follow)
        suggestions = User.query.filter(
            User.id != current_user.id,
            ~User.followers.any(followers.c.follower_id == current_user.id)
        ).order_by(db.func.random()).limit(5).all()

        return render_template('social/feed.html', posts=posts, suggestions=suggestions, comment_form=CommentForm())

    @app.route('/profile/<username>')
    def profile(username):
        user = User.query.filter_by(username=username).first_or_404()
        page = request.args.get('page', 1, type=int)
        posts = Post.query.filter_by(user_id=user.id).order_by(Post.created_at.desc()).paginate(
            page=page, per_page=12, error_out=False)

        # Get follower and following counts
        followers_count = user.followers.count()
        following_count = user.followed.count()

        # Check if current user is following this profile
        is_following = False
        if current_user.is_authenticated:
            is_following = current_user.is_following(user)

        return render_template('social/profile.html', user=user, posts=posts,
                              followers_count=followers_count, following_count=following_count,
                              is_following=is_following)

    @app.route('/profile/edit', methods=['GET', 'POST'])
    @login_required
    def edit_profile():
        form = ProfileForm()
        if form.validate_on_submit():
            if form.profile_image.data:
                picture_file = save_profile_picture(form.profile_image.data)
                current_user.profile_image = picture_file

            current_user.bio = form.bio.data
            current_user.location = form.location.data
            current_user.website = form.website.data

            db.session.commit()
            flash('Your profile has been updated!', 'success')
            return redirect(url_for('profile', username=current_user.username))

        elif request.method == 'GET':
            form.bio.data = current_user.bio
            form.location.data = current_user.location
            form.website.data = current_user.website

        return render_template('social/edit_profile.html', form=form)

    @app.route('/post/new', methods=['GET', 'POST'])
    @login_required
    def new_post():
        form = PostForm()
        if form.validate_on_submit():
            if form.image.data:
                picture_file = save_post_image(form.image.data)
                post = Post(
                    image_filename=picture_file,
                    caption=form.caption.data,
                    user_id=current_user.id
                )
                db.session.add(post)
                db.session.commit()
                flash('Your post has been created!', 'success')
                return redirect(url_for('feed'))

        return render_template('social/create_post.html', form=form, title='New Post')

    @app.route('/post/<int:post_id>')
    def post(post_id):
        post = Post.query.get_or_404(post_id)
        comments = post.comments.order_by(Comment.created_at.asc()).all()
        return render_template('social/post.html', post=post, comments=comments, form=CommentForm())

    @app.route('/post/<int:post_id>/like', methods=['POST'])
    @login_required
    def like_post(post_id):
        post = Post.query.get_or_404(post_id)
        like = Like.query.filter_by(user_id=current_user.id, post_id=post.id).first()

        if like:
            # User already liked the post - unlike it
            db.session.delete(like)
        else:
            # Add a new like
            like = Like(user_id=current_user.id, post_id=post.id)
            db.session.add(like)

        db.session.commit()
        return redirect(request.referrer or url_for('feed'))

    @app.route('/post/<int:post_id>/comment', methods=['POST'])
    @login_required
    def comment_post(post_id):
        post = Post.query.get_or_404(post_id)
        form = CommentForm()

        if form.validate_on_submit():
            comment = Comment(
                content=form.content.data,
                user_id=current_user.id,
                post_id=post.id
            )
            db.session.add(comment)
            db.session.commit()
            flash('Your comment has been posted!', 'success')

        return redirect(request.referrer or url_for('post', post_id=post.id))

    @app.route('/post/<int:post_id>/delete', methods=['POST'])
    @login_required
    def delete_post(post_id):
        post = Post.query.get_or_404(post_id)

        # Make sure the current user is the author of the post
        if post.user_id != current_user.id and not current_user.is_admin:
            abort(403)  # Forbidden

        # Delete the image file
        if post.image_filename:
            image_path = os.path.join(current_app.static_folder, 'uploads', 'posts', post.image_filename)
            if os.path.exists(image_path):
                os.remove(image_path)

        db.session.delete(post)
        db.session.commit()
        flash('Your post has been deleted!', 'success')
        return redirect(url_for('profile', username=current_user.username))

    @app.route('/follow/<username>', methods=['POST'])
    @login_required
    def follow(username):
        user = User.query.filter_by(username=username).first_or_404()

        # Can't follow yourself
        if user == current_user:
            flash('You cannot follow yourself!', 'danger')
            return redirect(url_for('profile', username=username))

        current_user.follow(user)
        db.session.commit()
        flash(f'You are now following {username}!', 'success')
        return redirect(url_for('profile', username=username))

    @app.route('/unfollow/<username>', methods=['POST'])
    @login_required
    def unfollow(username):
        user = User.query.filter_by(username=username).first_or_404()

        if user == current_user:
            flash('You cannot unfollow yourself!', 'danger')
            return redirect(url_for('profile', username=username))

        current_user.unfollow(user)
        db.session.commit()
        flash(f'You have unfollowed {username}.', 'success')
        return redirect(url_for('profile', username=username))

    @app.route('/search', methods=['GET', 'POST'])
    def search_users():
        form = SearchForm()
        users = []

        if form.validate_on_submit() or request.args.get('query'):
            query = form.query.data or request.args.get('query')
            users = User.query.filter(User.username.contains(query) | 
                                      User.bio.contains(query) | 
                                      User.location.contains(query)).all()

        # Get popular users for suggestions
        popular_users = User.query.order_by(db.func.count(followers.c.followed_id).desc()).limit(6).all()

        return render_template('social/search.html', form=form, users=users, popular_users=popular_users)

    @app.route('/followers/<username>')
    def followers_list(username):
        user = User.query.filter_by(username=username).first_or_404()
        followers = user.followers.all()
        return render_template('social/connections.html', users=followers, title=f"{username}'s Followers")

    @app.route('/following/<username>')
    def following_list(username):
        user = User.query.filter_by(username=username).first_or_404()
        following = user.followed.all()
        return render_template('social/connections.html', users=following, title=f"{username} is Following")

    # Authentication routes
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('feed'))

        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(email=form.email.data).first()

            if user and user.check_password(form.password.data):
                login_user(user, remember=form.remember.data)
                next_page = request.args.get('next')
                if next_page and next_page.startswith('/'):
                    return redirect(next_page)
                return redirect(url_for('home'))
            else:
                flash('Login unsuccessful. Please check email and password', 'danger')

        return render_template('login.html', form=form)

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('home'))

        form = RegistrationForm()
        if form.validate_on_submit():
            user = User(
                username=form.username.data,
                email=form.email.data
            )
            user.set_password(form.password.data)

            db.session.add(user)
            db.session.commit()

            flash('Your account has been created! You can now log in.', 'success')
            return redirect(url_for('login'))

        return render_template('register.html', form=form)

    @app.route('/logout')
    def logout():
        logout_user()
        return redirect(url_for('home'))

    # Livestream routes
    @app.route('/livestreams')
    def livestreams():
        """Display all livestreams, with currently live ones first"""
        live_streams = Livestream.query.filter_by(is_live=True).order_by(Livestream.started_at.desc()).all()
        upcoming_streams = Livestream.query.filter(
            Livestream.is_live==False, 
            Livestream.scheduled_time > datetime.utcnow()
        ).order_by(Livestream.scheduled_time).all()
        past_streams = Livestream.query.filter(
            Livestream.is_live==False,
            Livestream.ended_at.isnot(None)
        ).order_by(Livestream.ended_at.desc()).limit(10).all()

        return render_template('livestreams.html', 
                              live_streams=live_streams,
                              upcoming_streams=upcoming_streams,
                              past_streams=past_streams)

    @app.route('/livestreams/<int:livestream_id>')
    def view_livestream(livestream_id):
        """View a specific livestream"""
        livestream = Livestream.query.get_or_404(livestream_id)
        comment_form = LivestreamCommentForm()
        comments = livestream.comments.order_by(LivestreamComment.created_at.desc()).all()

        return render_template('livestream.html', 
                              livestream=livestream,
                              comments=comments,
                              form=comment_form)

    @app.route('/livestreams/new', methods=['GET', 'POST'])
    @login_required
    def new_livestream():
        """Create a new livestream"""
        form = LivestreamForm()

        if form.validate_on_submit():
            # Generate a unique stream key
            stream_key = secrets.token_hex(16)

            # Save thumbnail if provided
            thumbnail = 'default_stream_thumbnail.jpg'
            if form.thumbnail.data:
                # Save the thumbnail
                random_hex = secrets.token_hex(8)
                _, f_ext = os.path.splitext(form.thumbnail.data.filename)
                thumbnail_fn = random_hex + f_ext
                thumbnail_path = os.path.join(current_app.static_folder, 'uploads', 'thumbnails', thumbnail_fn)

                # Ensure the directory exists
                os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)

                # Resize and save the image
                output_size = (1280, 720)  # 16:9 aspect ratio
                i = Image.open(form.thumbnail.data)
                i.thumbnail(output_size, Image.LANCZOS)
                i.save(thumbnail_path)

                thumbnail = thumbnail_fn

            livestream = Livestream(
                title=form.title.data,
                description=form.description.data,
                stream_key=stream_key,
                scheduled_time=form.scheduled_time.data,
                thumbnail=thumbnail,
                user_id=current_user.id
            )

            db.session.add(livestream)
            db.session.commit()

            flash('Your livestream has been created!', 'success')
            return redirect(url_for('view_livestream', livestream_id=livestream.id))

        return render_template('new_livestream.html', form=form)

    @app.route('/livestreams/<int:livestream_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_livestream(livestream_id):
        """Edit an existing livestream"""
        livestream = Livestream.query.get_or_404(livestream_id)

        # Check if the current user is the owner of the livestream
        if livestream.user_id != current_user.id and not current_user.is_admin:
            abort(403)  # Forbidden

        form = LivestreamForm()

        if form.validate_on_submit():
            livestream.title = form.title.data
            livestream.description = form.description.data
            livestream.scheduled_time = form.scheduled_time.data

            # Update thumbnail if provided
            if form.thumbnail.data:
                # Save the thumbnail
                random_hex = secrets.token_hex(8)
                _, f_ext = os.path.splitext(form.thumbnail.data.filename)
                thumbnail_fn = random_hex + f_ext
                thumbnail_path = os.path.join(current_app.static_folder, 'uploads', 'thumbnails', thumbnail_fn)

                # Ensure the directory exists
                os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)

                # Resize and save the image
                output_size = (1280, 720)  # 16:9 aspect ratio
                i = Image.open(form.thumbnail.data)
                i.thumbnail(output_size, Image.LANCZOS)
                i.save(thumbnail_path)

                # Delete old thumbnail if it's not the default
                if livestream.thumbnail != 'default_stream_thumbnail.jpg':
                    old_thumbnail_path = os.path.join(current_app.static_folder, 'uploads', 'thumbnails', livestream.thumbnail)
                    if os.path.exists(old_thumbnail_path):
                        os.remove(old_thumbnail_path)

                livestream.thumbnail = thumbnail_fn

            db.session.commit()

            flash('Your livestream has been updated!', 'success')
            return redirect(url_for('view_livestream', livestream_id=livestream.id))

        elif request.method == 'GET':
            form.title.data = livestream.title
            form.description.data = livestream.description
            form.scheduled_time.data = livestream.scheduled_time

        return render_template('edit_livestream.html', form=form, livestream=livestream)

    @app.route('/livestreams/<int:livestream_id>/start', methods=['POST'])
    @login_required
    def start_livestream(livestream_id):
        """Start a livestream"""
        livestream = Livestream.query.get_or_404(livestream_id)

        # Check if the current user is the owner of the livestream
        if livestream.user_id != current_user.id:
            abort(403)  # Forbidden

        # Check if the livestream is already live
        if livestream.is_live:
            flash('This livestream is already live!', 'warning')
            return redirect(url_for('view_livestream', livestream_id=livestream.id))

        livestream.is_live = True
        livestream.started_at = datetime.utcnow()
        db.session.commit()

        flash('Your livestream has started!', 'success')
        return redirect(url_for('view_livestream', livestream_id=livestream.id))

    @app.route('/livestreams/<int:livestream_id>/end', methods=['POST'])
    @login_required
    def end_livestream(livestream_id):
        """End a livestream"""
        livestream = Livestream.query.get_or_404(livestream_id)

        # Check if the current user is the owner of the livestream
        if livestream.user_id != current_user.id:
            abort(403)  # Forbidden

        # Check if the livestream is live
        if not livestream.is_live:
            flash('This livestream is not currently live!', 'warning')
            return redirect(url_for('view_livestream', livestream_id=livestream.id))

        livestream.is_live = False
        livestream.ended_at = datetime.utcnow()
        db.session.commit()

        flash('Your livestream has ended!', 'success')
        return redirect(url_for('view_livestream', livestream_id=livestream.id))

    @app.route('/livestreams/<int:livestream_id>/comment', methods=['POST'])
    @login_required
    def comment_livestream(livestream_id):
        """Add a comment to a livestream"""
        livestream = Livestream.query.get_or_404(livestream_id)
        form = LivestreamCommentForm()

        if form.validate_on_submit():
            comment = LivestreamComment(
                content=form.content.data,
                user_id=current_user.id,
                livestream_id=livestream.id
            )

            db.session.add(comment)
            db.session.commit()

            flash('Your comment has been posted!', 'success')

        return redirect(url_for('view_livestream', livestream_id=livestream.id))

    @app.route('/livestreams/<int:livestream_id>/delete', methods=['POST'])
    @login_required
    def delete_livestream(livestream_id):
        """Delete a livestream"""
        livestream = Livestream.query.get_or_404(livestream_id)

        # Check if the current user is the owner of the livestream or an admin
        if livestream.user_id != current_user.id and not current_user.is_admin:
            abort(403)  # Forbidden

        # Delete thumbnail if it's not the default
        if livestream.thumbnail != 'default_stream_thumbnail.jpg':
            thumbnail_path = os.path.join(current_app.static_folder, 'uploads', 'thumbnails', livestream.thumbnail)
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)

        db.session.delete(livestream)
        db.session.commit()

        flash('Your livestream has been deleted!', 'success')
        return redirect(url_for('livestreams'))

    # Admin livestream management
    @app.route('/admin/livestreams')
    @login_required
    @admin_required
    def admin_livestreams():
        """Admin view for managing livestreams"""
        livestreams = Livestream.query.order_by(Livestream.created_at.desc()).all()
        return render_template('admin/livestreams.html', livestreams=livestreams)

    # Error handlers
    @app.errorhandler(404)
    def page_not_found(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    return app



def init_db(app):
    """Initialize database with required data"""
    with app.app_context():
        # Create all database tables
        db.create_all()
        print("Database tables created")

        try:
            # Create initial data if the database is empty
            if not ForumCategory.query.first():
                categories = [
                    ForumCategory(name='General Discussion', description='Talk about anything related to our community.'),
                    ForumCategory(name='Help & Support', description='Ask questions and get help from community members.'),
                    ForumCategory(name='Ideas & Suggestions', description='Share your ideas for improving our community.'),
                    ForumCategory(name='Events', description='Discussions about upcoming and past events.')
                ]
                db.session.add_all(categories)

                # Create admin user if it doesn't exist
                if not User.query.filter_by(email='admin@example.com').first():
                    admin = User(
                        username='admin',
                        email='admin@example.com',
                        is_admin=True
                    )
                    admin.set_password('adminpassword')
                    db.session.add(admin)

                db.session.commit()
                print("Initial data created successfully!")
            else:
                print("Database already contains data, skipping initialization")
        except Exception as e:
            db.session.rollback()
            print(f"Error initializing database: {e}")
            raise

# Create an application instance only when run directly
if __name__ == '__main__':
    app = create_app(os.getenv('FLASK_ENV', 'development'))
    init_db(app)  # Initialize the database when running directly
    app.run()
