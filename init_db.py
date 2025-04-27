import os
import secrets
from dotenv import load_dotenv
from app import create_app, db
from models import User, ForumCategory, Livestream
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

def init_db():
    """Initialize the database with initial data."""
    app = create_app('development')

    with app.app_context():
        # Create default admin user if it doesn't exist
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
        admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'adminpassword')

        if not User.query.filter_by(email=admin_email).first():
            admin = User(
                username=admin_username,
                email=admin_email,
                password_hash=generate_password_hash(admin_password),
                is_admin=True
            )
            db.session.add(admin)
            print(f"Created admin user: {admin_username}")

        # Create forum categories if they don't exist
        if not ForumCategory.query.first():
            categories = [
                ForumCategory(name='General Discussion', description='Talk about anything related to our community.'),
                ForumCategory(name='Help & Support', description='Ask questions and get help from community members.'),
                ForumCategory(name='Ideas & Suggestions', description='Share your ideas for improving our community.'),
                ForumCategory(name='Events', description='Discussions about upcoming and past events.')
            ]
            db.session.add_all(categories)
            print("Created forum categories")

        # Create sample livestreams if they don't exist
        if not Livestream.query.first():
            # Get the admin user for creating livestreams
            admin = User.query.filter_by(is_admin=True).first()

            if admin:
                # Create a currently live stream
                live_stream = Livestream(
                    title="Welcome to GrowHaven Livestream",
                    description="This is our first official livestream where we'll discuss upcoming community events and gardening tips.",
                    stream_key=secrets.token_hex(16),
                    is_live=True,
                    started_at=datetime.utcnow() - timedelta(minutes=30),
                    thumbnail="default_stream_thumbnail.jpg",
                    user_id=admin.id
                )

                # Create an upcoming stream
                upcoming_stream = Livestream(
                    title="Seasonal Planting Guide",
                    description="Join us for a comprehensive guide on what to plant this season for optimal growth and harvest.",
                    stream_key=secrets.token_hex(16),
                    scheduled_time=datetime.utcnow() + timedelta(days=2),
                    thumbnail="default_stream_thumbnail.jpg",
                    user_id=admin.id
                )

                # Create a past stream
                past_stream = Livestream(
                    title="Community Garden Tour",
                    description="Take a virtual tour of our community gardens and see the amazing work our members have been doing.",
                    stream_key=secrets.token_hex(16),
                    is_live=False,
                    started_at=datetime.utcnow() - timedelta(days=5, hours=2),
                    ended_at=datetime.utcnow() - timedelta(days=5),
                    thumbnail="default_stream_thumbnail.jpg",
                    user_id=admin.id
                )

                db.session.add_all([live_stream, upcoming_stream, past_stream])
                print("Created sample livestreams")

        # Commit the changes
        db.session.commit()
        print("Database initialized successfully!")

if __name__ == '__main__':
    init_db()
