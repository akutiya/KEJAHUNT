from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


# =====================
# USER MODEL
# =====================
class User(UserMixin, db.Model):

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), nullable=True)

    username = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(200),
        nullable=False
    )

    role = db.Column(
        db.String(20),
        default="user"
    )


# =====================
# PROPERTY MODEL
# =====================
class Property(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)

    price = db.Column(db.Integer, nullable=False)

    location = db.Column(db.String(200), nullable=False)

    bedrooms = db.Column(db.Integer, nullable=False)
    bathrooms = db.Column(db.Integer, nullable=False)

    image_file = db.Column(db.String(300), nullable=True)

    phone = db.Column(db.String(20), nullable=True)

    landlord_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id'),
        nullable=False
    )