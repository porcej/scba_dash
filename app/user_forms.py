from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, PasswordField
from wtforms.validators import DataRequired, Length, Optional


class UserForm(FlaskForm):
    """Form for creating/editing users"""
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Password', validators=[Optional(), Length(min=6)])
    is_admin = BooleanField('Admin', default=False)

