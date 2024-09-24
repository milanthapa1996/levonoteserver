import os
from dotenv import load_dotenv

load_dotenv()


SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI", "sqlite:///default.db")  # Default value added
SQLALCHEMY_TRACK_MODIFICATIONS = os.environ.get("SQLALCHEMY_TRACK_MODIFICATIONS", False)  # Default value added
MAIL_SERVER = os.environ.get("MAIL_SERVER")
MAIL_PORT = os.environ.get("MAIL_PORT")
MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS")
MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER")