import uuid
import os
import secrets

from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from sqlalchemy import or_, text

from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from models import db, User, Property, Favorite, Message

app = Flask(__name__)

# CONFIG
app.config['SECRET_KEY'] = 'kejahunt-secret-key'

basedir = os.path.abspath(os.path.dirname(__file__))

app.config['SQLALCHEMY_DATABASE_URI'] = (
    'sqlite:///' + os.path.join(basedir, 'kejahunt.db')
)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join(basedir, 'static/uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db.init_app(app)

# LOGIN MANAGER
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# CREATE DATABASE AND PROPERTY STATUS TABLE
with app.app_context():
    db.create_all()

    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS property_listing_status (
            property_id INTEGER PRIMARY KEY,
            status VARCHAR(20) NOT NULL DEFAULT 'Available'
        )
    """))
    db.session.commit()


def get_property_status(property_id):
    """Return a property's saved status."""
    row = db.session.execute(
        text("""
            SELECT status
            FROM property_listing_status
            WHERE property_id = :pid
        """),
        {"pid": property_id}
    ).first()

    if row and row[0] in ("Available", "Rented"):
        return row[0]

    return "Available"


def set_property_status(property_id, status):
    """Save or update a property's availability status."""
    db.session.execute(
        text("""
            INSERT INTO property_listing_status (property_id, status)
            VALUES (:pid, :status)
            ON CONFLICT(property_id)
            DO UPDATE SET status = excluded.status
        """),
        {
            "pid": property_id,
            "status": status
        }
    )
    db.session.commit()


def attach_property_status(properties):
    """Attach the saved status to each property for template display."""
    for prop in properties:
        prop.status = get_property_status(prop.id)

    return properties


# HOME
@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    return render_template('index.html')


# REGISTER
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        role = request.form['role']

        if role not in ('user', 'landlord'):
            return "Invalid account role.", 400

        if User.query.filter_by(email=email).first():
            return "Email already exists."

        if User.query.filter_by(username=username).first():
            return "Username already exists."

        hashed_password = generate_password_hash(password)

        new_user = User(
            username=username,
            email=email,
            password=hashed_password,
            role=role
        )

        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for('login'))

    return render_template('register.html')


# LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))

        return "Invalid email or password."

    return render_template('login.html')


# DASHBOARD ROUTER
@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == "landlord":
        return redirect(url_for('landlord_dashboard'))

    return redirect(url_for('user_dashboard'))


# USER DASHBOARD
@app.route('/user_dashboard')
@login_required
def user_dashboard():
    if current_user.role != "user":
        return redirect(url_for('dashboard'))

    return render_template(
        'dashboard/user_dashboard.html',
        user=current_user
    )


# LANDLORD DASHBOARD
@app.route('/landlord_dashboard')
@login_required
def landlord_dashboard():
    if current_user.role != "landlord":
        return redirect(url_for('dashboard'))

    return render_template(
        'dashboard/landlord_dashboard.html',
        user=current_user
    )


# LOGOUT
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


# =====================================================
# PROPERTY SYSTEM
# =====================================================

# ADD PROPERTY
@app.route('/add_property', methods=['GET', 'POST'])
@login_required
def add_property():
    if current_user.role != "landlord":
        return "Only landlords can add properties.", 403

    if request.method == 'POST':
        image = request.files.get('image')
        filename = None

        if image and image.filename:
            safe_name = secure_filename(image.filename)

            if not safe_name:
                return "Invalid image filename.", 400

            filename = str(uuid.uuid4()) + "_" + safe_name

            image.save(
                os.path.join(app.config['UPLOAD_FOLDER'], filename)
            )

        new_property = Property(
            title=request.form['title'],
            description=request.form['description'],
            price=request.form['price'],
            location=request.form['location'],
            bedrooms=request.form['bedrooms'],
            bathrooms=request.form['bathrooms'],
            image_file=filename,
            phone=request.form['phone'],
            landlord_id=current_user.id
        )

        db.session.add(new_property)
        db.session.commit()

        # New listings are Available by default.
        set_property_status(new_property.id, "Available")

        flash("Property added successfully.", "success")
        return redirect(url_for('my_properties'))

    return render_template('add_property.html')


# =====================================================
# LANDLORD PROPERTY MANAGEMENT
# =====================================================

@app.route('/my_properties')
@login_required
def my_properties():
    if current_user.role != "landlord":
        return redirect(url_for("dashboard"))

    search = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip()

    query = Property.query.filter_by(
        landlord_id=current_user.id
    )

    if search:
        query = query.filter(
            or_(
                Property.title.contains(search),
                Property.location.contains(search),
                Property.description.contains(search)
            )
        )

    properties_list = query.order_by(
        Property.id.desc()
    ).all()

    attach_property_status(properties_list)

    if status_filter in ("Available", "Rented"):
        properties_list = [
            prop for prop in properties_list
            if prop.status == status_filter
        ]

    all_properties = Property.query.filter_by(
        landlord_id=current_user.id
    ).all()

    attach_property_status(all_properties)

    total_count = len(all_properties)

    available_count = sum(
        1 for prop in all_properties
        if prop.status == "Available"
    )

    rented_count = sum(
        1 for prop in all_properties
        if prop.status == "Rented"
    )

    return render_template(
        "my_properties.html",
        properties=properties_list,
        search=search,
        status_filter=status_filter,
        total_count=total_count,
        available_count=available_count,
        rented_count=rented_count
    )


# EDIT A PROPERTY
@app.route('/edit_property/<int:property_id>', methods=['GET', 'POST'])
@login_required
def edit_property(property_id):
    if current_user.role != "landlord":
        return redirect(url_for("dashboard"))

    prop = Property.query.filter_by(
        id=property_id,
        landlord_id=current_user.id
    ).first_or_404()

    prop.status = get_property_status(prop.id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("price", "").strip()
        location = request.form.get("location", "").strip()
        phone = request.form.get("phone", "").strip()
        bedrooms = request.form.get("bedrooms", "").strip()
        bathrooms = request.form.get("bathrooms", "").strip()
        property_type = request.form.get("property_type", "").strip()
        status = request.form.get("status", "Available").strip()

        if not all((title, description, price, location, phone)):
            flash("Please complete all required fields.", "error")
            return redirect(
                url_for("edit_property", property_id=prop.id)
            )

        if status not in ("Available", "Rented"):
            status = "Available"

        image = request.files.get("image")
        new_filename = None

        # Only replace the existing image when a new image is selected.
        if image and image.filename:
            allowed_extensions = {"png", "jpg", "jpeg", "webp"}

            if "." not in image.filename:
                flash(
                    "Please upload a PNG, JPG, JPEG, or WEBP image.",
                    "error"
                )
                return redirect(
                    url_for("edit_property", property_id=prop.id)
                )

            extension = image.filename.rsplit(".", 1)[1].lower()

            if extension not in allowed_extensions:
                flash(
                    "Please upload a PNG, JPG, JPEG, or WEBP image.",
                    "error"
                )
                return redirect(
                    url_for("edit_property", property_id=prop.id)
                )

            safe_name = secure_filename(image.filename)

            if not safe_name:
                flash("The image filename is invalid.", "error")
                return redirect(
                    url_for("edit_property", property_id=prop.id)
                )

            new_filename = str(uuid.uuid4()) + "_" + safe_name

            image.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    new_filename
                )
            )

        old_filename = prop.image_file

        prop.title = title
        prop.description = description
        prop.price = price
        prop.location = location
        prop.phone = phone
        prop.bedrooms = bedrooms or None
        prop.bathrooms = bathrooms or None

        if hasattr(prop, "property_type"):
            prop.property_type = property_type or None

        if new_filename:
            prop.image_file = new_filename

        try:
            db.session.commit()
            set_property_status(prop.id, status)

        except Exception:
            db.session.rollback()

            if new_filename:
                new_path = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    new_filename
                )

                if os.path.isfile(new_path):
                    os.remove(new_path)

            flash(
                "The property could not be updated. "
                "Please check the details and try again.",
                "error"
            )

            return redirect(
                url_for("edit_property", property_id=prop.id)
            )

        # Remove the old photo only after the new one has been saved.
        if new_filename and old_filename:
            old_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                old_filename
            )

            if os.path.isfile(old_path):
                try:
                    os.remove(old_path)
                except OSError:
                    pass

        flash("Property updated successfully.", "success")
        return redirect(url_for("my_properties"))

    return render_template(
        "edit_property.html",
        property=prop
    )


# MARK PROPERTY AS AVAILABLE OR RENTED
@app.route('/property_status/<int:property_id>', methods=['POST'])
@login_required
def property_status(property_id):
    if current_user.role != "landlord":
        return redirect(url_for("dashboard"))

    prop = Property.query.filter_by(
        id=property_id,
        landlord_id=current_user.id
    ).first_or_404()

    status = request.form.get("status", "").strip()

    if status not in ("Available", "Rented"):
        flash("Invalid property status.", "error")
    else:
        set_property_status(prop.id, status)
        flash("Property status updated.", "success")

    return redirect(url_for("my_properties"))


# DELETE PROPERTY
@app.route('/delete_property/<int:property_id>', methods=['POST'])
@login_required
def delete_property(property_id):
    if current_user.role != "landlord":
        return redirect(url_for("dashboard"))

    prop = Property.query.filter_by(
        id=property_id,
        landlord_id=current_user.id
    ).first_or_404()

    image_filename = prop.image_file

    try:
        # Remove saved-property records associated with this listing.
        Favorite.query.filter_by(
            property_id=prop.id
        ).delete(synchronize_session=False)

        # Do not delete the property if related messages prevent deletion.
        db.session.delete(prop)
        db.session.commit()

        db.session.execute(
            text("""
                DELETE FROM property_listing_status
                WHERE property_id = :pid
            """),
            {"pid": property_id}
        )
        db.session.commit()

    except Exception:
        db.session.rollback()

        flash(
            "This property could not be deleted. It may be linked "
            "to existing messages. Your listing may need further review.",
            "error"
        )

        return redirect(url_for("my_properties"))

    if image_filename:
        image_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            image_filename
        )

        if os.path.isfile(image_path):
            try:
                os.remove(image_path)
            except OSError:
                pass

    flash("Property deleted successfully.", "success")
    return redirect(url_for("my_properties"))


# =====================================================
# PUBLIC PROPERTY SEARCH AND LISTINGS
# =====================================================

@app.route('/properties')
def properties():
    query = request.args.get('q', '').strip()

    property_query = Property.query

    if query:
        property_query = property_query.filter(
            or_(
                Property.title.contains(query),
                Property.location.contains(query),
                Property.description.contains(query)
            )
        )

    props = property_query.all()

    # Add availability to the public listing objects too.
    attach_property_status(props)

    return render_template(
        'properties.html',
        properties=props,
        query=query
    )


# PROPERTY DETAILS
@app.route('/property/<int:property_id>')
def property_details(property_id):
    prop = Property.query.get_or_404(property_id)
    prop.status = get_property_status(prop.id)

    return render_template(
        'property_details.html',
        property=prop
    )


# SAVE PROPERTY
@app.route('/save/<int:property_id>')
@login_required
def save_property(property_id):
    prop = Property.query.get_or_404(property_id)

    existing = Favorite.query.filter_by(
        user_id=current_user.id,
        property_id=prop.id
    ).first()

    if existing:
        return redirect(url_for('properties'))

    favorite = Favorite(
        user_id=current_user.id,
        property_id=prop.id
    )

    db.session.add(favorite)
    db.session.commit()

    return redirect(url_for('properties'))


# VIEW SAVED PROPERTIES
@app.route('/saved')
@login_required
def saved_properties():
    favorites = Favorite.query.filter_by(
        user_id=current_user.id
    ).all()

    return render_template(
        'saved.html',
        favorites=favorites
    )


# REMOVE SAVED PROPERTY
@app.route('/unsave/<int:property_id>')
@login_required
def unsave_property(property_id):
    favorite = Favorite.query.filter_by(
        user_id=current_user.id,
        property_id=property_id
    ).first()

    if favorite:
        db.session.delete(favorite)
        db.session.commit()

    return redirect(url_for('saved_properties'))


# =====================================================
# MESSAGING SYSTEM
# =====================================================

# SEND MESSAGE TO LANDLORD
@app.route("/message/<int:property_id>", methods=["POST"])
@login_required
def send_message(property_id):
    prop = Property.query.get_or_404(property_id)

    if current_user.id == prop.landlord_id:
        return "You cannot message yourself about your own property.", 400

    message_text = request.form.get("message", "").strip()

    if not message_text:
        return "Message cannot be empty.", 400

    msg = Message(
        sender_id=current_user.id,
        receiver_id=prop.landlord_id,
        property_id=prop.id,
        message=message_text
    )

    db.session.add(msg)
    db.session.commit()

    return redirect(url_for(
        "property_details",
        property_id=prop.id
    ))


# LANDLORD MESSAGES
# Conversations are grouped by contact, not by property.
@app.route("/messages")
@login_required
def messages():
    if current_user.role != "landlord":
        return redirect(url_for("dashboard"))

    all_messages = Message.query.filter(
        or_(
            Message.sender_id == current_user.id,
            Message.receiver_id == current_user.id
        )
    ).order_by(Message.id.asc()).all()

    grouped = {}

    for msg in all_messages:
        if msg.sender_id == current_user.id:
            other_user = msg.receiver
        else:
            other_user = msg.sender

        if other_user is None:
            continue

        other_id = other_user.id

        if other_id not in grouped:
            grouped[other_id] = {
                "contact": other_user,
                "messages": [],
                "reference_id": msg.id,
                "last_message": msg
            }

        grouped[other_id]["messages"].append(msg)
        grouped[other_id]["reference_id"] = msg.id
        grouped[other_id]["last_message"] = msg

    conversations = sorted(
        grouped.values(),
        key=lambda conversation: conversation["reference_id"],
        reverse=True
    )

    return render_template(
        "messages.html",
        conversations=conversations
    )


# REPLY WITHIN THE SAME CONVERSATION
@app.route("/reply/<int:id>", methods=["GET", "POST"])
@login_required
def reply(id):
    msg = Message.query.get_or_404(id)

    if current_user.id not in (msg.sender_id, msg.receiver_id):
        return "Unauthorized", 403

    if request.method == "POST":
        message_text = request.form.get("message", "").strip()

        if not message_text:
            return jsonify({
                "success": False,
                "error": "Please enter a message."
            }), 400

        if msg.sender_id == current_user.id:
            recipient_id = msg.receiver_id
        else:
            recipient_id = msg.sender_id

        new_message = Message(
            sender_id=current_user.id,
            receiver_id=recipient_id,
            property_id=msg.property_id,
            message=message_text
        )

        db.session.add(new_message)
        db.session.commit()

        return jsonify({
            "success": True,
            "id": new_message.id,
            "sender_id": current_user.id,
            "sender_name": current_user.username,
            "message": new_message.message
        })

    return render_template(
        "reply.html",
        message=msg
    )


# HOUSE HUNTER MESSAGES
@app.route("/my_messages")
@login_required
def my_messages():
    msgs = Message.query.filter(
        or_(
            Message.sender_id == current_user.id,
            Message.receiver_id == current_user.id
        )
    ).order_by(Message.id.asc()).all()

    return render_template(
        "my_messages.html",
        messages=msgs
    )


# INBOX ROUTER
@app.route("/inbox")
@login_required
def inbox():
    if current_user.role == "landlord":
        return redirect(url_for("messages"))

    return redirect(url_for("my_messages"))


# =====================================================
# MOBILE API ROUTES
# =====================================================

# API REGISTER
@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()

    if not data:
        return jsonify({'message': 'No data received'}), 400

    email = data.get('email')
    full_name = data.get('full_name')
    password = data.get('password')
    role = data.get('role')

    if not email or not full_name or not password or not role:
        return jsonify({'message': 'Missing required fields'}), 400

    if role not in ('user', 'landlord'):
        return jsonify({'message': 'Invalid role'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'message': 'Email already exists'}), 400

    if User.query.filter_by(username=email).first():
        return jsonify({'message': 'User already exists'}), 400

    hashed_password = generate_password_hash(password)
    token = secrets.token_hex(16)

    new_user = User(
        username=email,
        email=email,
        password=hashed_password,
        role=role,
        token=token
    )

    db.session.add(new_user)
    db.session.commit()

    return jsonify({
        'message': 'Registered successfully',
        'role': role,
        'full_name': full_name,
        'email': email,
        'token': token
    }), 201


# API LOGIN
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()

    if not data:
        return jsonify({'message': 'No data received'}), 400

    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()

    if not user or not check_password_hash(user.password, password):
        return jsonify({'message': 'Invalid credentials'}), 401

    token = secrets.token_hex(16)
    user.token = token
    db.session.commit()

    return jsonify({
        'message': 'Login successful',
        'role': user.role,
        'full_name': user.username,
        'email': user.email,
        'token': token
    }), 200


# API GET PROPERTIES
@app.route('/api/properties', methods=['GET'])
def get_properties():
    props = Property.query.all()
    result = []

    for prop in props:
        landlord = User.query.get(prop.landlord_id)

        result.append({
            'id': prop.id,
            'title': prop.title,
            'location': prop.location,
            'price': str(prop.price),
            'description': prop.description,
            'image_url': prop.image_file,
            'landlord_name': landlord.username if landlord else 'Unknown',
            'landlord_id': prop.landlord_id,
            'status': get_property_status(prop.id)
        })

    return jsonify(result)


# API POST PROPERTY
@app.route('/api/properties', methods=['POST'])
def api_post_property():
    token = request.headers.get(
        'Authorization', ''
    ).replace('Bearer ', '')

    user = User.query.filter_by(token=token).first()

    if not user or user.role != 'landlord':
        return jsonify({'message': 'Unauthorized'}), 401

    title = request.form.get('title')
    location = request.form.get('location')
    price = request.form.get('price')
    description = request.form.get('description')
    property_type = request.form.get('property_type')

    if not all((title, location, price, description)):
        return jsonify({
            'message': 'Title, location, price and description are required'
        }), 400

    filename = None

    image = request.files.get('image')

    if image and image.filename:
        safe_name = secure_filename(image.filename)

        if not safe_name:
            return jsonify({'message': 'Invalid image filename'}), 400

        filename = str(uuid.uuid4()) + "_" + safe_name

        image.save(
            os.path.join(app.config['UPLOAD_FOLDER'], filename)
        )

    new_property = Property(
        title=title,
        location=location,
        price=price,
        description=description,
        property_type=property_type,
        landlord_id=user.id,
        phone='',
        bedrooms=0,
        bathrooms=0,
        image_file=filename
    )

    db.session.add(new_property)
    db.session.commit()

    set_property_status(new_property.id, "Available")

    return jsonify({
        'message': 'Property posted successfully',
        'id': new_property.id
    }), 201


# RUN APPLICATION
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)