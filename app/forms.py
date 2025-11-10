from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField, DateTimeField, PasswordField, SelectField
from wtforms.validators import DataRequired, Optional, Length
from wtforms.widgets import TextArea

ALERT_COLOR_CHOICES = [
    ('primary', 'Primary'),
    ('secondary', 'Secondary'),
    ('success', 'Success'),
    ('danger', 'Danger'),
    ('warning', 'Warning'),
    ('info', 'Info'),
    ('dark', 'Dark'),
    ('light', 'Light')
]


class TaskForm(FlaskForm):
    """Form for creating/editing tasks"""
    content = TextAreaField('Task Content', validators=[DataRequired(), Length(min=1, max=1000)])
    completed = BooleanField('Completed', default=False)
    priority = SelectField('Priority', 
                          choices=[(1, 'High'), (2, 'Medium'), (3, 'Low')],
                          coerce=int,
                          default=2,
                          validators=[DataRequired()])


class AlertForm(FlaskForm):
    """Form for creating/editing alerts"""
    message = TextAreaField('Message', validators=[DataRequired(), Length(min=1, max=1000)], 
                           widget=TextArea(), render_kw={"rows": 4})
    start_time = DateTimeField('Start Time', validators=[Optional()], 
                              format='%Y-%m-%dT%H:%M')
    end_time = DateTimeField('End Time', validators=[DataRequired()], 
                            format='%Y-%m-%dT%H:%M')
    color_theme = SelectField('Color Theme', choices=ALERT_COLOR_CHOICES, default='danger', validators=[DataRequired()])


class ScrapeConfigForm(FlaskForm):
    """Form for pstrax credentials configuration"""
    pstrax_base_url = StringField('Base URL', validators=[Optional(), Length(max=255)])
    pstrax_username = StringField('Username', validators=[Optional(), Length(max=255)])
    pstrax_password = PasswordField('Password', validators=[Optional()])
    scrape_interval = StringField('Scrape Interval (minutes)', validators=[Optional()])


class PasswordChangeForm(FlaskForm):
    """Form for changing user password"""
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6, message='Password must be at least 6 characters long')])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired()])

