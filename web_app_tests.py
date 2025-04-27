import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_home_page(client):
    rv = client.get('/')
    assert rv.status_code == 200

def test_about_page(client):
    rv = client.get('/about')
    assert rv.status_code == 200

def test_contact_page(client):
    rv = client.get('/contact')
    assert rv.status_code == 200