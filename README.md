# GrowHaven - Community Platform

GrowHaven is a community platform that enables users to connect, share knowledge, participate in forums, and support fundraising campaigns.

## Features

- User authentication (register, login, logout)
- Community forum with categories and topics
- Fundraising campaigns with donation tracking
- Livestreaming functionality for community broadcasts
- Contact form for user inquiries

## Technologies Used

- Python 3.12
- Flask web framework
- SQLAlchemy ORM
- PostgreSQL database
- Flask-Login for authentication
- Flask-WTF for form handling
- Gunicorn WSGI server
- Docker and Docker Compose

## Installation and Setup

### Prerequisites

- Python 3.12 or higher
- PostgreSQL
- pip (Python package manager)
- Docker and Docker Compose (optional)

### Local Development Setup

1. Clone the repository:
   ```
   git clone https://github.com/your-username/growhaven.git
   cd growhaven
   ```

2. Create and activate a virtual environment:
   ```
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install the dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Create a `.env` file based on `.env.example`:
   ```
   cp .env.example .env
   ```

5. Edit the `.env` file with your configuration values.

6. Initialize the database:
   ```
   flask db upgrade
   ```

7. Start the development server:
   ```
   flask run
   ```

8. Visit `http://127.0.0.1:5000` in your browser.

### Docker Setup

1. Build and start the Docker containers:
   ```
   docker-compose up -d
   ```

2. Visit `http://127.0.0.1:5000` in your browser.

## Production Deployment

### Using Docker

1. Set up your production environment variables in `.env`.
2. Build and deploy using Docker Compose:
   ```
   docker-compose -f docker-compose.yml up -d
   ```

### Manual Deployment

1. Set up your production environment variables.
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set up a PostgreSQL database and update your database URL in the environment variables.
4. Initialize the database:
   ```
   flask db upgrade
   ```
5. Run using Gunicorn:
   ```
   gunicorn --bind 0.0.0.0:5000 wsgi:app
   ```
6. Set up Nginx as a reverse proxy (recommended).

## Security Considerations

- Always use HTTPS in production
- Set up proper database backups
- Keep dependencies updated
- Use strong, unique passwords for all accounts
- Implement rate-limiting for login attempts
- Regularly review logs for suspicious activities

## Livestreaming Setup

The platform includes livestreaming functionality that allows users to broadcast to the community.

### Requirements

1. Create a default thumbnail image:
   - Create a file named `default_stream_thumbnail.jpg` 
   - Place it in the `static/uploads/thumbnails/` directory
   - Recommended size: 1280x720 pixels (16:9 aspect ratio)

2. RTMP Server Setup:
   - For actual livestreaming functionality, you'll need to set up an RTMP server
   - We recommend using [Nginx-RTMP](https://github.com/arut/nginx-rtmp-module) or [OBS.Ninja](https://obs.ninja/)
   - Configure the RTMP server to push streams to the `static/hls/` directory

3. Streaming Software:
   - Users can stream using [OBS Studio](https://obsproject.com/) or similar software
   - Stream URL format: `rtmp://your-server-address/live`
   - Stream key: Unique key generated for each livestream

## Testing

Run the test suite with pytest:
