from app import create_app, init_db

# Create the application
app = create_app('production')

# Initialize the database when the module is imported
# This ensures tables are created before the first request
init_db(app)

# Run the app when executed directly
if __name__ == '__main__':
    app.run()
