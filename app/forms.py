from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField, DateTimeField, PasswordField, SelectField, IntegerField
from wtforms.validators import DataRequired, Optional, Length, NumberRange
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
    scrape_interval = StringField('Alerts scrape interval (minutes)', validators=[Optional()])
    equipment_scrape_interval_hours = StringField(
        'Equipment sync interval (hours)', validators=[Optional()]
    )
    default_alert_color = SelectField('Default Alert Color', choices=ALERT_COLOR_CHOICES, default='danger', validators=[DataRequired()])
    alerts_font_size = IntegerField('Alerts Font Size (px)', default=16, validators=[Optional(), NumberRange(min=12, max=48)])
    gear_list_type_ids = StringField('SCBA Gear List Type IDs', validators=[Optional(), Length(max=255)])
    gear_list_statuses = StringField('SCBA Gear List Statuses', validators=[Optional(), Length(max=255)])


class FillSiteForm(FlaskForm):
    """Form for creating/editing fill sites"""
    name = StringField('Name', validators=[DataRequired(), Length(min=1, max=128)])


class FillBoardForm(FlaskForm):
    """Form for creating/editing fill boards"""
    name = StringField('Name', validators=[DataRequired(), Length(min=1, max=128)])
    fill_site_id = SelectField('Fill Site', coerce=int, validators=[DataRequired()])


class PasswordChangeForm(FlaskForm):
    """Form for changing user password"""
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6, message='Password must be at least 6 characters long')])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired()])

