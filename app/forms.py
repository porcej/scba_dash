from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField, DateTimeField, PasswordField
from wtforms.validators import DataRequired, Optional, Length
from wtforms.widgets import TextArea


class TaskForm(FlaskForm):
    """Form for creating/editing tasks"""
    content = TextAreaField('Task Content', validators=[DataRequired(), Length(min=1, max=1000)])
    completed = BooleanField('Completed', default=False)


class AlertForm(FlaskForm):
    """Form for creating/editing alerts"""
    message = TextAreaField('Message', validators=[DataRequired(), Length(min=1, max=1000)], 
                           widget=TextArea(), render_kw={"rows": 4})
    start_time = DateTimeField('Start Time', validators=[Optional()], 
                              format='%Y-%m-%dT%H:%M')
    end_time = DateTimeField('End Time', validators=[DataRequired()], 
                            format='%Y-%m-%dT%H:%M')


class ScrapeConfigForm(FlaskForm):
    """Form for pstrax credentials configuration"""
    pstrax_base_url = StringField('Base URL', validators=[Optional(), Length(max=255)])
    pstrax_username = StringField('Username', validators=[Optional(), Length(max=255)])
    pstrax_password = PasswordField('Password', validators=[Optional()])
    scrape_interval = StringField('Scrape Interval (minutes)', validators=[Optional()])

