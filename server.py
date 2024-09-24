from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_mail import Mail, Message
from flask_apscheduler import APScheduler
from datetime import datetime, timedelta, UTC, timezone
from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from sqlalchemy.dialects.postgresql import UUID
import uuid
import config

app = Flask(__name__)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = config.SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = config.SQLALCHEMY_TRACK_MODIFICATIONS
app.config['MAIL_SERVER'] = config.MAIL_SERVER
app.config['MAIL_PORT'] = config.MAIL_PORT
app.config['MAIL_USE_TLS'] = config.MAIL_USE_TLS
app.config['MAIL_USERNAME'] = config.MAIL_USERNAME
app.config['MAIL_PASSWORD'] = config.MAIL_PASSWORD
app.config['MAIL_DEFAULT_SENDER'] = config.MAIL_DEFAULT_SENDER

# Initialize extensions
db = SQLAlchemy(app)
mail = Mail(app)


app.config['SCHEDULER_JOBSTORES'] = {
    'default': SQLAlchemyJobStore(url=app.config['SQLALCHEMY_DATABASE_URI'])
}
app.config['SCHEDULER_API_ENABLED'] = True
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# Enable CORS
CORS(app)

# Models
class Note(db.Model):
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_pinned = db.Column(db.Boolean, default=False)
    has_reminder = db.Column(db.Boolean, default=False)
    reminder_datetime = db.Column(db.DateTime, nullable=True)
    reminder_email = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_archived = db.Column(db.Boolean, default=False)
    is_trashed = db.Column(db.Boolean, default=False)

# Helper Functions
def send_reminder_email(note_id):
    with app.app_context():
        note = Note.query.get(note_id)
        if note and note.has_reminder and note.reminder_email:
            try:
                msg = Message(
                    subject=f"Reminder: {note.title}",
                    recipients=[note.reminder_email],
                    body=f"{note.content}"
                )
                mail.send(msg)
                app.logger.info(f"Reminder email sent for note {note.id} to {note.reminder_email}")
                
                # Clear the reminder after sending
                note.has_reminder = False
                note.reminder_datetime = None
                db.session.commit()
            except Exception as e:
                app.logger.error(f"Failed to send reminder email for note {note.id}: {str(e)}")
        else:
            app.logger.warning(f"Attempted to send reminder for non-existent or invalid note: {note_id}")

def check_missed_reminders():
    with app.app_context():
        current_time = datetime.now(UTC)
        missed_reminders = Note.query.filter(
            Note.has_reminder == True,
            Note.reminder_datetime <= current_time,
            Note.reminder_datetime > (current_time - timedelta(days=1))  # Limit to last 24 hours
        ).all()
        
        for note in missed_reminders:
            send_reminder_email(note.id)
            app.logger.info(f"Sent missed reminder for note {note.id}")


# Routes
@app.route('/notes', methods=['GET'])
def get_notes():
    notes = Note.query.filter_by(is_archived=False, is_trashed=False).all()
    return jsonify([{
        'id': note.id,
        'title': note.title,
        'content': note.content,
        'is_pinned': note.is_pinned,
        'has_reminder': note.has_reminder,
        'reminder_datetime': note.reminder_datetime.isoformat() if note.reminder_datetime else None,
        'reminder_email': note.reminder_email,
        'created_at': note.created_at.isoformat(),
        'updated_at': note.updated_at.isoformat(),
        'is_archived': note.is_archived,
        'is_trashed': note.is_trashed
    } for note in notes])

@app.route('/notes', methods=['POST'])
def create_note():
    data = request.json
    new_note = Note(
        title=data['title'],
        content=data['content'],
        is_pinned=data.get('is_pinned', False),
        has_reminder=data.get('has_reminder', False),
        reminder_datetime=datetime.fromisoformat(data['reminder_datetime']).replace(tzinfo=UTC) if data.get('reminder_datetime') else None,
        reminder_email=data.get('reminder_email'),
        is_archived=data.get('is_archived', False),
        is_trashed=data.get('is_trashed', False)
    )
    db.session.add(new_note)
    db.session.commit()

    # If a reminder is set, schedule it
    if new_note.has_reminder and new_note.reminder_datetime:
        scheduler.add_job(
            id=f'reminder_{new_note.id}',
            func=send_reminder_email,
            trigger='date',
            run_date=new_note.reminder_datetime,
            args=[new_note.id]
        )

    return jsonify({
        'message': 'Note created successfully',
        'note': {
            'id': new_note.id,
            'title': new_note.title,
            'content': new_note.content,
            'is_pinned': new_note.is_pinned,
            'has_reminder': new_note.has_reminder,
            'reminder_datetime': new_note.reminder_datetime.isoformat() if new_note.reminder_datetime else None,
            'reminder_email': new_note.reminder_email,
            'created_at': new_note.created_at.isoformat(),
            'updated_at': new_note.updated_at.isoformat(),
            'is_archived': new_note.is_archived,
            'is_trashed': new_note.is_trashed
        }
    }), 201

@app.route('/notes/<uuid:note_id>', methods=['PUT'])
def update_note(note_id):
    note = Note.query.get_or_404(note_id)
    data = request.json

    note.title = data.get('title', note.title)
    note.content = data.get('content', note.content)
    note.is_pinned = data.get('is_pinned', note.is_pinned)
    note.is_archived = data.get('is_archived', note.is_archived)
    note.is_trashed = data.get('is_trashed', note.is_trashed)
    note.has_reminder = data.get('has_reminder', note.has_reminder)
    note.reminder_datetime = datetime.fromisoformat(data['reminder_datetime']).replace(tzinfo=UTC) if data.get('reminder_datetime') else None,
    note.reminder_email = data.get('email', note.reminder_email)

    db.session.commit()

    # If a reminder is set, schedule it
    if note.has_reminder and note.reminder_datetime:
        scheduler.add_job(
            id=f'reminder_{note.id}',
            func=send_reminder_email,
            trigger='date',
            run_date=note.reminder_datetime,
            args=[note.id]
        )

    return jsonify({
        'message': 'Note updated successfully',
        'note': {
            'id': note.id,
            'title': note.title,
            'content': note.content,
            'is_pinned': note.is_pinned,
            'has_reminder': note.has_reminder,
            'reminder_datetime': note.reminder_datetime.isoformat() if note.reminder_datetime else None,
            'reminder_email': note.reminder_email,
            'created_at': note.created_at.isoformat(),
            'updated_at': note.updated_at.isoformat(),
            'is_archived': note.is_archived,
            'is_trashed': note.is_trashed
        }
    })

@app.route('/notes/<uuid:note_id>', methods=['DELETE'])
def delete_note(note_id):
    note = Note.query.get_or_404(note_id)
    note.is_archived = False
    note.is_pinned = False
    note.is_trashed = True
    db.session.commit()
    return jsonify({'message': 'Note moved to trash'})

@app.route('/notes/<uuid:note_id>/archive', methods=['PUT'])
def archive_note(note_id):
    note = Note.query.get_or_404(note_id)
    note.is_pinned = False
    note.is_trashed = False
    note.is_archived = True
    db.session.commit()
    return jsonify({'message': 'Note archived successfully'})

@app.route('/archives', methods=['GET'])
def get_archived_notes():
    archived_notes = Note.query.filter_by(is_archived=True, is_trashed=False).all()
    return jsonify([{
        'id': note.id,
        'title': note.title,
        'content': note.content,
        'updated_at': note.updated_at
    } for note in archived_notes])

@app.route('/trash', methods=['GET'])
def get_trashed_notes():
    trashed_notes = Note.query.filter_by(is_trashed=True).all()
    return jsonify([{
        'id': note.id,
        'title': note.title,
        'content': note.content,
        'updated_at': note.updated_at
    } for note in trashed_notes])

@app.route('/reminders', methods=['GET'])
def get_reminders():
    reminders = Note.query.filter_by(has_reminder=True, is_archived=False, is_trashed=False).all()
    return jsonify([{
        'id': note.id,
        'title': note.title,
        'content': note.content,
        'reminder_datetime': note.reminder_datetime,
        'reminder_email': note.reminder_email,
        'updated_at': note.updated_at
    } for note in reminders])

@app.route('/notes/<uuid:note_id>/restore', methods=['PUT'])
def restore_note(note_id):
    note = Note.query.get_or_404(note_id)
    note.is_trashed = False
    note.is_archived = False
    db.session.commit()
    return jsonify({'message': 'Note restored successfully'})

@app.route('/notes/<uuid:note_id>/permanent-delete', methods=['DELETE'])
def permanent_delete_note(note_id):
    note = Note.query.get_or_404(note_id)
    db.session.delete(note)
    db.session.commit()
    return jsonify({'message': 'Note permanently deleted'})

@app.route('/notes/<uuid:note_id>', methods=['GET'])
def get_single_note(note_id):
    note = Note.query.get_or_404(note_id)
    return jsonify({
        'id': note.id,
        'title': note.title,
        'content': note.content,
        'is_pinned': note.is_pinned,
        'has_reminder': note.has_reminder,
        'reminder_datetime': note.reminder_datetime.isoformat() if note.reminder_datetime else None,
        'reminder_email': note.reminder_email,
        'created_at': note.created_at.isoformat(),
        'updated_at': note.updated_at.isoformat(),
        'is_archived': note.is_archived,
        'is_trashed': note.is_trashed
    })

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        check_missed_reminders()
    app.run(debug=True, port=8080)