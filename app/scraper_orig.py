import requests
import re
import json
from urllib.parse import urlparse, urljoin, quote
from bs4 import BeautifulSoup
from datetime import datetime
from app import db
from app.models import ScrapeConfig, ScrapeData
from app.socketio_events import emit_scrape_update


class PstraxScraper:
    """Web scraper for pstrax website"""
    
    def __init__(self):
        self.session = requests.Session()
        # Note: We don't include Accept-Encoding for gzip/br because requests handles it automatically
        # But sometimes explicit compression can cause issues, so we'll let requests handle it natively
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        # Cookies are automatically persisted by requests.Session() across all requests
        # This means cookies set by the server are automatically stored and sent with subsequent requests
        # Note: Session storage (window.sessionStorage) is JavaScript-only and cannot be accessed via requests
        # However, any session data stored in cookies will be automatically handled
        self.session.cookies.clear()  # Start with empty cookies for fresh session
        
    def get_cookies_info(self):
        """Get information about current cookies for debugging"""
        cookie_info = {}
        for cookie in self.session.cookies:
            cookie_info[cookie.name] = {
                'value': cookie.value[:50] if len(cookie.value) > 50 else cookie.value,  # Truncate long values
                'domain': cookie.domain,
                'path': cookie.path,
                'secure': cookie.secure,
                'expires': str(cookie.expires) if cookie.expires else None
            }
        return cookie_info
    
    def login(self, username, password, base_url='https://pstrax.com'):
        """
        Login to pstrax website
        
        Args:
            username: Username for login
            password: Password for login
            base_url: Base URL of pstrax website
        
        Returns:
            tuple: (bool: success, dict: error_details)
        """
        error_details = {
            'step': None,
            'status_code': None,
            'message': None,
            'url': None
        }
        
        try:
            # Try multiple possible login URLs (PHP sites often use login.php)
            login_urls_to_try = [
                f'{base_url.rstrip("/")}/login.php',  # Most common for PHP sites
                f'{base_url.rstrip("/")}/login',
                base_url  # Sometimes login form is at root
            ]
            response = None
            login_url = None
            
            error_details['step'] = 'accessing_login_page'
            for url in login_urls_to_try:
                error_details['url'] = url
                try:
                    response = self.session.get(url, timeout=10, stream=False)
                    error_details['status_code'] = response.status_code
                    
                    # Check if response is valid HTML (not binary/compressed improperly)
                    if response.status_code == 200:
                        # Check content encoding
                        content_encoding = response.headers.get('content-encoding', '').lower()
                        if content_encoding and 'gzip' not in content_encoding and 'deflate' not in content_encoding:
                            print(f"Warning: Unusual content encoding: {content_encoding}")
                        
                        # Ensure proper encoding - requests should auto-decompress, but let's verify
                        try:
                            # Force decoding - requests should have already decompressed
                            response.encoding = response.apparent_encoding or response.encoding or 'utf-8'
                            
                            # Check raw content first few bytes to detect if it's still compressed
                            raw_preview = response.content[:10]
                            is_likely_binary = raw_preview.startswith(b'\x1f\x8b') or raw_preview.startswith(b'\x78') or any(b > 127 for b in raw_preview[:5] if b < 32)
                            
                            if is_likely_binary and len(response.text) < 100:
                                print(f"Warning: Response might still be compressed, attempting manual decode")
                                # Try to manually handle if requests missed it
                                import gzip
                                try:
                                    decompressed = gzip.decompress(response.content)
                                    response._content = decompressed
                                    response.encoding = 'utf-8'
                                    response._text = None  # Force re-parse
                                except:
                                    pass
                            
                            # Now check if we have valid HTML
                            text_preview = response.text[:200] if response.text else ''
                            if text_preview and ('<' in text_preview or 'html' in text_preview.lower() or 'form' in text_preview.lower()):
                                login_url = url
                                break
                            else:
                                print(f"Response from {url} doesn't look like HTML: {text_preview[:100]}")
                        except Exception as decode_error:
                            print(f"Error decoding response from {url}: {decode_error}")
                            continue
                except requests.RequestException as e:
                    print(f"Error accessing {url}: {e}")
                    continue
            
            if not response or response.status_code != 200:
                error_details['message'] = f"Failed to access login page: Tried {login_urls_to_try}, last status {error_details.get('status_code', 'unknown')}"
                print(error_details['message'])
                return False, error_details
            
            # Verify we have valid HTML content
            if not response.text or len(response.text) < 50:
                error_details['message'] = f"Login page response is empty or too short"
                error_details['response_length'] = len(response.text) if response.text else 0
                print(error_details['message'])
                return False, error_details
            
            # Try to detect if content is actually HTML
            response_text_lower = response.text.lower()
            if not ('<' in response.text[:500] or 'html' in response_text_lower[:500] or 'form' in response_text_lower[:500]):
                error_details['message'] = f"Login page doesn't appear to contain HTML content"
                error_details['content_preview'] = response.text[:200] if len(response.text) > 200 else response.text
                error_details['content_type'] = response.headers.get('content-type', 'unknown')
                print(error_details['message'])
                print(f"Content-Type: {error_details['content_type']}")
                return False, error_details
            
            # Parse login form
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # STEP 1: Submit username first (two-step login process)
            # Find initial login form - try multiple strategies
            error_details['step'] = 'finding_login_form'
            form = (soup.find('form', {'method': 'post'}) or 
                   soup.find('form', method='POST') or
                   soup.find('form') or
                   soup.find('form', class_=lambda x: x and 'login' in x.lower() if x else False))
            
            if not form:
                error_details['message'] = "Login form not found in page"
                print(error_details['message'])
                # Try to find all forms for debugging
                all_forms = soup.find_all('form')
                error_details['forms_found'] = len(all_forms)
                if all_forms:
                    error_details['form_actions'] = [f.get('action', 'no action') for f in all_forms]
                # Save a snippet of HTML for debugging
                error_details['page_snippet'] = response.text[:500] if len(response.text) > 500 else response.text
                return False, error_details
            
            # Prepare field name possibilities
            possible_username_fields = [
                'username', 'user', 'email', 'login', 'user_name', 'userName', 
                'UserName', 'user_login', 'account', 'account_name', 'login_name',
                'usr', 'usrname', 'uname', 'uid', 'userid', 'user_id'
            ]
            
            # Find username field in initial form
            username_field = None
            username_field_name = None
            
            # Try exact name/id match first
            for field_name in possible_username_fields:
                username_field = (form.find('input', {'name': field_name}) or 
                                form.find('input', {'id': field_name}))
                if username_field:
                    username_field_name = username_field.get('name') or username_field.get('id')
                    break
            
            # If not found, try by type='text' and placeholder/label
            if not username_field:
                text_inputs = form.find_all('input', {'type': 'text'}) + form.find_all('input', type=None)
                for inp in text_inputs:
                    placeholder = (inp.get('placeholder', '') or '').lower()
                    inp_id = (inp.get('id', '') or '').lower()
                    inp_name = (inp.get('name', '') or '').lower()
                    if any(keyword in placeholder or keyword in inp_id or keyword in inp_name 
                           for keyword in ['user', 'login', 'email', 'account']):
                        username_field = inp
                        username_field_name = inp.get('name') or inp.get('id')
                        break
            
            if not username_field:
                error_details['step'] = 'finding_username_field'
                error_details['message'] = "Could not find username field in initial form"
                all_inputs = form.find_all('input')
                error_details['inputs_found'] = [
                    {
                        'name': i.get('name'), 
                        'id': i.get('id'), 
                        'type': i.get('type'),
                        'placeholder': i.get('placeholder'),
                        'class': i.get('class')
                    } 
                    for i in all_inputs
                ]
                error_details['form_html_snippet'] = str(form)[:1000] if form else 'No form'
                print(error_details['message'])
                return False, error_details
            
            # Prepare first step data (username only)
            step1_data = {}
            if username_field_name:
                step1_data[username_field_name] = username
            
            # Include CSRF tokens and hidden inputs
            for hidden_input in form.find_all('input', type='hidden'):
                input_name = hidden_input.get('name')
                input_value = hidden_input.get('value', '')
                if input_name:
                    step1_data[input_name] = input_value
            
            # Check for CSRF in meta tags
            csrf_meta = soup.find('meta', {'name': 'csrf-token'}) or soup.find('meta', attrs={'name': lambda x: x and 'csrf' in x.lower()})
            if csrf_meta:
                csrf_value = csrf_meta.get('content')
                if csrf_value:
                    for csrf_field in ['csrf_token', '_token', 'authenticity_token', 'csrf-token', 'csrfmiddlewaretoken']:
                        if csrf_field not in step1_data:
                            step1_data[csrf_field] = csrf_value
                            break
            
            # Submit username (STEP 1)
            error_details['step'] = 'submitting_username'
            action = form.get('action', '')
            if action:
                if action.startswith('http'):
                    step1_post_url = action
                elif action.startswith('/'):
                    step1_post_url = f"{base_url.rstrip('/')}{action}"
                else:
                    step1_post_url = f"{base_url.rstrip('/')}/{action}"
            else:
                step1_post_url = login_url
            
            error_details['url'] = step1_post_url
            error_details['step1_data_keys'] = list(step1_data.keys())
            
            response = self.session.post(step1_post_url, data=step1_data, timeout=10, allow_redirects=True)
            error_details['status_code'] = response.status_code
            error_details['step1_response_url'] = response.url
            
            # Log cookies after step 1
            cookies_after_step1 = list(self.session.cookies.keys())
            if cookies_after_step1:
                print(f"Cookies after step 1 (username submission): {cookies_after_step1}")
                error_details['cookies_after_step1'] = self.get_cookies_info()
            
            print(f"Step 1 response: Status {response.status_code}, URL: {response.url}")
            
            # If we got redirected away from login, might have been auto-login or error
            if 'login' not in response.url.lower() and response.status_code in [200, 301, 302, 303, 307, 308]:
                # Check if this is actually a successful login
                response_lower = response.text.lower()
                if (username.lower() in response_lower or 
                    'logout' in response_lower or 
                    'dashboard' in response_lower):
                    # URL-encode the redirect URL in case it contains special characters like @
                    redirect_url = response.url
                    # Parse and reconstruct to ensure proper encoding
                    parsed = urlparse(redirect_url)
                    # Reconstruct with proper encoding (preserve slashes, encode @ as %40)
                    redirect_url = f"{parsed.scheme}://{parsed.netloc}{quote(parsed.path, safe='/')}"
                    if parsed.query:
                        redirect_url += f"?{quote(parsed.query, safe='=&')}"
                    if parsed.fragment:
                        redirect_url += f"#{quote(parsed.fragment)}"
                    print(f"Login successful after username submission (URL: {redirect_url})")
                    return True, {'redirect_url': redirect_url}
            
            # STEP 2: Parse the response to get the form with both username and password fields
            error_details['step'] = 'parsing_second_form'
            
            # Ensure proper encoding
            response.encoding = response.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Log the response URL to see if we were redirected
            print(f"Parsing step 2 form from URL: {response.url}")
            
            # First, check if password field exists anywhere on the page (might be dynamically added)
            password_field = None
            password_field_name = None
            all_password_fields = soup.find_all('input', {'type': 'password'})
            
            # Also check for password fields that might be hidden or have different attributes
            # Some sites use input type="text" with password-related names
            all_inputs_on_page = soup.find_all('input')
            password_like_fields = []
            for inp in all_inputs_on_page:
                inp_type = (inp.get('type', '') or '').lower()
                inp_name = (inp.get('name', '') or '').lower()
                inp_id = (inp.get('id', '') or '').lower()
                if (inp_type == 'password' or 
                    'password' in inp_name or 
                    'password' in inp_id or
                    (inp_type == 'text' and ('pass' in inp_name or 'pass' in inp_id))):
                    password_like_fields.append(inp)
            
            # IMPORTANT: Check HTML comments for password field (common pattern for JS-rendered fields)
            # Some sites have password fields in HTML comments that are uncommented via JavaScript
            if not all_password_fields and not password_like_fields:
                print("Checking HTML comments for password field...")
                # Look for password field in HTML comments using regex
                import re
                # Pattern to match password input in comments
                comment_pattern = r'<!--[^>]*<input[^>]*(?:id|name)=["\']([^"\']*password[^"\']*)["\'][^>]*type=["\']password["\']'
                comment_matches = re.findall(comment_pattern, response.text, re.IGNORECASE)
                if comment_matches:
                    password_field_name = comment_matches[0]
                    print(f"Found password field name in HTML comments: {password_field_name}")
                    # Also try to extract more info from comments
                    full_pattern = r'<!--[^>]*<input[^>]*id=["\']([^"\']+)["\'][^>]*name=["\']([^"\']+)["\'][^>]*type=["\']password["\']'
                    full_match = re.search(full_pattern, response.text, re.IGNORECASE | re.DOTALL)
                    if full_match:
                        password_field_name = full_match.group(2) or full_match.group(1)
                        print(f"Extracted password field: {password_field_name}")
            
            if all_password_fields:
                password_field = all_password_fields[0]
                password_field_name = password_field.get('name') or password_field.get('id')
                print(f"Found password field: {password_field_name}")
            elif password_like_fields:
                # Use password-like field
                password_field = password_like_fields[0]
                password_field_name = password_field.get('name') or password_field.get('id')
                print(f"Found password-like field: {password_field_name}")
            elif password_field_name:
                # We found the field name in comments, create a virtual field object
                print(f"Using password field from HTML comments: {password_field_name}")
                # We'll use this name directly when submitting
            else:
                print("No password field found anywhere on the page")
                # Save page content for debugging
                error_details['page_snippet'] = response.text[:2000] if len(response.text) > 2000 else response.text
                error_details['all_input_types'] = list(set([inp.get('type', 'none') for inp in all_inputs_on_page]))
                error_details['all_input_names'] = [inp.get('name') for inp in all_inputs_on_page if inp.get('name')]
            
            # Find the form - try multiple strategies
            form = None
            forms = soup.find_all('form')
            
            # Strategy 1: Find form that contains the password field we just found
            if password_field:
                form = password_field.find_parent('form')
            
            # Strategy 2: Look for forms that contain a password field
            if not form:
                for f in forms:
                    password_inputs = f.find_all('input', {'type': 'password'})
                    if password_inputs:
                        form = f
                        break
            
            # Strategy 3: Look for POST forms (most likely login form)
            if not form:
                for f in forms:
                    if f.get('method', '').lower() == 'post':
                        form = f
                        break
            
            # Strategy 4: Look for forms with login-related actions or IDs
            if not form:
                for f in forms:
                    action = (f.get('action', '') or '').lower()
                    form_id = (f.get('id', '') or '').lower()
                    if 'login' in action or 'password' in action or 'login' in form_id:
                        form = f
                        break
            
            # Strategy 5: If we found a password field, try to find the nearest form
            if not form and password_field:
                # Find parent container and look for form within it
                parent = password_field.find_parent(['form', 'div', 'section'])
                if parent:
                    # Look for form in parent hierarchy
                    if parent.name == 'form':
                        form = parent
                    else:
                        form = parent.find('form')
            
            # Fallback: use first form
            if not form and forms:
                form = forms[0]
                print(f"Using fallback: first form found (total forms: {len(forms)})")
            
            if not form:
                error_details['message'] = "Form not found after username submission"
                all_forms = soup.find_all('form')
                error_details['forms_found'] = len(all_forms)
                error_details['password_fields_found'] = len(all_password_fields) if 'all_password_fields' in locals() else 0
                error_details['response_snippet'] = response.text[:1000] if len(response.text) > 1000 else response.text
                print(error_details['message'])
                return False, error_details
            
            # Now find both username and password fields
            username_field = None
            username_field_name = None
            
            # If we already found password field above, use it
            # Otherwise, try to find it in the form
            if not password_field:
                all_inputs = form.find_all('input')
                password_fields_in_form = form.find_all('input', {'type': 'password'})
                if password_fields_in_form:
                    password_field = password_fields_in_form[0]
                    password_field_name = password_field.get('name') or password_field.get('id')
            
            # Find ALL input fields for debugging
            all_inputs = form.find_all('input')
            
            # Find username field - check ALL input types (text, hidden, readonly, disabled)
            # Case-insensitive matching for field names
            form_inputs = form.find_all('input')
            for inp in form_inputs:
                # Skip password fields
                if inp.get('type', '').lower() == 'password':
                    continue
                
                inp_name = (inp.get('name') or '').lower()
                inp_id = (inp.get('id') or '').lower()
                
                # Check against possible username field names (case-insensitive)
                for field_name in possible_username_fields:
                    if field_name.lower() == inp_name or field_name.lower() == inp_id:
                        username_field = inp
                        username_field_name = inp.get('name') or inp.get('id')
                        break
                
                if username_field:
                    break
            
            # If still not found, try by placeholder/label and other attributes
            if not username_field:
                for inp in form_inputs:
                    if inp.get('type', '').lower() == 'password':
                        continue
                    
                    placeholder = (inp.get('placeholder', '') or '').lower()
                    inp_id = (inp.get('id', '') or '').lower()
                    inp_name = (inp.get('name', '') or '').lower()
                    inp_type = (inp.get('type', '') or '').lower()
                    
                    # Check for username indicators
                    if (any(keyword in placeholder or keyword in inp_id or keyword in inp_name 
                           for keyword in ['user', 'login', 'email', 'account', 'name']) and
                        inp_type in ['text', 'email', 'hidden', '']):
                        username_field = inp
                        username_field_name = inp.get('name') or inp.get('id')
                        break
            
            # Also check labels associated with inputs
            if not username_field and password_field:
                # Try to find username field near the password field
                password_parent = password_field.find_parent()
                if password_parent:
                    # Look for text inputs in the same parent container
                    nearby_inputs = password_parent.find_all('input', {'type': ['text', 'email']}, limit=5)
                    for inp in nearby_inputs:
                        if inp.get('type', '').lower() != 'password':
                            username_field = inp
                            username_field_name = inp.get('name') or inp.get('id')
                            break
            
            # Final check: if password field exists but no username field found,
            # check if username might be in a hidden field or readonly field
            if password_field and not username_field:
                # Check hidden fields
                hidden_inputs = form.find_all('input', type='hidden')
                for inp in hidden_inputs:
                    inp_name = (inp.get('name', '') or '').lower()
                    if any(field in inp_name for field in possible_username_fields):
                        # Check if it has a value (might be from step 1)
                        if inp.get('value'):
                            username_field = inp
                            username_field_name = inp.get('name')
                            break
            
            # If still no username field, try the first text input that's not password
            if password_field and not username_field:
                for inp in form_inputs:
                    inp_type = (inp.get('type', '') or '').lower()
                    if inp_type in ['text', 'email'] and inp != password_field:
                        username_field = inp
                        username_field_name = inp.get('name') or inp.get('id')
                        break
            
            # If we found password field name in comments, we can proceed
            # Otherwise check if password field exists
            if not password_field and not password_field_name:
                error_details['step'] = 'finding_password_field'
                error_details['message'] = "Password field not found in second form or page"
                error_details['inputs_found'] = [
                    {
                        'name': i.get('name'), 
                        'id': i.get('id'), 
                        'type': i.get('type'),
                        'placeholder': i.get('placeholder'),
                        'disabled': i.get('disabled'),
                        'readonly': i.get('readonly'),
                        'value': i.get('value', '')[:50] if i.get('value') else None
                    } 
                    for i in all_inputs
                ]
                error_details['form_html_snippet'] = str(form)[:2000] if form else 'No form'
                error_details['form_action'] = form.get('action', 'no action') if form else 'No form'
                error_details['form_method'] = form.get('method', 'no method') if form else 'No form'
                error_details['all_password_fields_on_page'] = len(all_password_fields)
                error_details['response_url'] = response.url
                error_details['page_title'] = soup.find('title')
                if error_details['page_title']:
                    error_details['page_title'] = error_details['page_title'].get_text(strip=True)
                print(error_details['message'])
                print(f"Form action: {error_details['form_action']}, Response URL: {response.url}")
                return False, error_details
            
            # If we only have password_field_name from comments but no actual field object,
            # that's okay - we'll use the name directly when submitting
            if password_field_name and not password_field:
                print(f"Using password field name '{password_field_name}' extracted from HTML comments")
                # Try common field names if the extracted one doesn't work
                if not password_field_name:
                    # Common password field names for this site
                    common_password_names = ['txtpassword', 'password', 'txt_password', 'user_password']
                    for pwd_name in common_password_names:
                        # Check if this name appears in the page (even in comments)
                        if pwd_name.lower() in response.text.lower():
                            password_field_name = pwd_name
                            print(f"Using common password field name: {password_field_name}")
                            break
            
            if not username_field:
                error_details['step'] = 'finding_username_field_step2'
                error_details['message'] = "Username field not found in second form (password field found)"
                error_details['password_field_found'] = True
                error_details['password_field_name'] = password_field_name
                # Still continue - we'll use the username variable directly
                username_field_name = None
                print(f"Warning: {error_details['message']}. Will attempt login without explicit username field.")
            
            # Prepare second step data (username + password)
            # Strategy: Include ALL inputs with names (to catch everything the form needs)
            step2_data = {}
            
            # First, collect ALL inputs with name attributes (except buttons)
            # This includes hidden, disabled, readonly, and visible fields
            all_named_inputs = []
            for inp in form.find_all(['input', 'textarea', 'select']):
                input_name = inp.get('name')
                input_type = (inp.get('type', '') or '').lower()
                
                # Skip submit buttons, but include everything else (even disabled/readonly)
                if input_name and input_type not in ['submit', 'button', 'reset', 'image']:
                    all_named_inputs.append(inp)
            
            # Add all named inputs first (this ensures we get CSRF tokens, hidden fields, etc.)
            for inp in all_named_inputs:
                input_name = inp.get('name')
                input_type = (inp.get('type', '') or '').lower()
                
                # Get value based on input type
                if input_type == 'password':
                    # Password will be set separately
                    continue
                elif input_type in ['checkbox', 'radio']:
                    if inp.get('checked'):
                        step2_data[input_name] = inp.get('value', 'on')
                elif inp.name == 'select':
                    # For select elements, get the selected option
                    selected = inp.find('option', selected=True) or inp.find('option', {'selected': 'selected'})
                    if selected:
                        step2_data[input_name] = selected.get('value', '')
                    elif inp.find('option'):
                        # Use first option if none selected
                        step2_data[input_name] = inp.find('option').get('value', '')
                elif inp.name == 'textarea':
                    step2_data[input_name] = (inp.string or '').strip()
                else:
                    # Regular input - use value attribute or empty string
                    input_value = inp.get('value', '')
                    step2_data[input_name] = input_value
            
            # Now override with specific username and password values
            # IMPORTANT: For PSTrax, the username field txtuser_name must be included in step 2
            # It may be pre-filled in the form, but we should still submit it
            
            # Add username - use the value from the field if it exists (might be pre-filled), otherwise use our username
            # For PSTrax specifically, look for txtuser_name
            if username_field and username_field_name:
                existing_value = username_field.get('value', '')
                if existing_value and existing_value.strip():
                    # Field already has a value - use it (might be the username from step 1)
                    step2_data[username_field_name] = existing_value
                    print(f"Using pre-filled username value: {existing_value[:20]}...")
                else:
                    # Field is empty - submit our username
                    step2_data[username_field_name] = username
                    print(f"Submitting username to field: {username_field_name}")
            elif username_field_name:
                # Field name was found but field object wasn't - still try to submit
                step2_data[username_field_name] = username
                print(f"Submitting username to field: {username_field_name}")
            elif not username_field_name:
                # Try to infer username field name from common patterns
                # For PSTrax, specifically check for txtuser_name
                if 'txtuser_name' not in step2_data:
                    # Check if txtuser_name field exists in the form
                    txtuser_field = form.find('input', {'name': 'txtuser_name'}) if form else None
                    if txtuser_field:
                        existing_val = txtuser_field.get('value', '')
                        if existing_val:
                            step2_data['txtuser_name'] = existing_val
                            username_field_name = 'txtuser_name'
                            print(f"Found pre-filled txtuser_name: {existing_val[:20]}...")
                        else:
                            step2_data['txtuser_name'] = username
                            username_field_name = 'txtuser_name'
                            print(f"Using txtuser_name field with provided username")
                
                # If still not set, try other common patterns
                if not username_field_name:
                    for field_name in possible_username_fields:
                        if field_name not in step2_data:
                            # Check if any input in the form might match
                            matching_inputs = form.find_all('input', {'name': field_name}) + form.find_all('input', {'id': field_name}) if form else []
                            if matching_inputs:
                                step2_data[field_name] = username
                                username_field_name = field_name
                                print(f"Using inferred username field: {field_name}")
                                break
                    
                    # If still not set, try the most common field names
                    if not username_field_name:
                        for common_name in ['username', 'user', 'email', 'login', 'txtuser_name']:
                            if common_name not in step2_data:
                                step2_data[common_name] = username
                                username_field_name = common_name
                                print(f"Using fallback username field: {common_name}")
                                break
            
            # Add password - this should override any existing password field value
            # Use the password_field_name we found (either from actual field or from HTML comments)
            if password_field_name:
                step2_data[password_field_name] = password
                print(f"Adding password to field: {password_field_name}")
            else:
                # Try to infer password field name from form
                password_inputs = form.find_all('input', {'type': 'password'}) if form else []
                if password_inputs:
                    pwd_name = password_inputs[0].get('name') or password_inputs[0].get('id')
                    if pwd_name:
                        step2_data[pwd_name] = password
                else:
                    # Last resort: try common password field names
                    common_names = ['txtpassword', 'password', 'txt_password', 'user_password', 'pwd']
                    for pwd_name in common_names:
                        if pwd_name not in step2_data:
                            step2_data[pwd_name] = password
                            password_field_name = pwd_name
                            print(f"Using fallback password field name: {password_field_name}")
                            break
            
            # Ensure we didn't accidentally include the password field twice or with wrong value
            # (it should only be set once with the actual password)
            
            # Check for CSRF in meta tags again (add all found tokens, not just one)
            csrf_meta_tags = soup.find_all('meta', attrs={'name': lambda x: x and ('csrf' in x.lower() or 'token' in x.lower())})
            for csrf_meta in csrf_meta_tags:
                csrf_value = csrf_meta.get('content')
                csrf_meta_name = csrf_meta.get('name', '').lower()
                if csrf_value:
                    # Try multiple CSRF field names based on meta tag name or common patterns
                    csrf_fields = ['csrf_token', '_token', 'authenticity_token', 'csrf-token', 'csrfmiddlewaretoken', '_csrf', 'token']
                    for csrf_field in csrf_fields:
                        # Use meta tag name as field name if it matches a pattern
                        if 'csrf' in csrf_meta_name and csrf_field not in step2_data:
                            step2_data[csrf_field] = csrf_value
                        elif csrf_field not in step2_data:
                            step2_data[csrf_field] = csrf_value
                    # Also try the meta tag name itself as a field name
                    if csrf_meta_name and csrf_meta_name not in step2_data:
                        step2_data[csrf_meta_name] = csrf_value
            
            # Also look for CSRF in script tags (some sites inject it there)
            for script in soup.find_all('script'):
                script_text = script.string or ''
                if 'csrf' in script_text.lower() or '_token' in script_text.lower():
                    # Try to extract token from script (basic regex)
                    token_patterns = [
                        r'csrf[_-]?token["\']?\s*[:=]\s*["\']([^"\']+)',
                        r'_token["\']?\s*[:=]\s*["\']([^"\']+)',
                    ]
                    for pattern in token_patterns:
                        match = re.search(pattern, script_text, re.IGNORECASE)
                        if match:
                            token_value = match.group(1)
                            for csrf_field in ['csrf_token', '_token']:
                                if csrf_field not in step2_data:
                                    step2_data[csrf_field] = token_value
                                    break
                            break
            
            # Submit username + password (STEP 2)
            error_details['step'] = 'submitting_login'
            action = form.get('action', '').strip()
            
            # Based on PSTrax login flow:
            # Step 1: Submit txtuser_name to /login-username
            # Step 2: Submit txtuser_name + txtpassword to /login (not /login-password!)
            step2_post_url = None
            
            # If the form action is still login-username, we should submit to /login instead
            if action and 'login-username' in action.lower():
                # Replace login-username with login for password submission
                if action.startswith('http://') or action.startswith('https://'):
                    # Full URL - replace login-username with login
                    step2_post_url = action.replace('/login-username', '/login').replace('login-username', 'login')
                elif action.startswith('/'):
                    # Absolute path
                    step2_post_url = action.replace('/login-username', '/login').replace('login-username', 'login')
                    parsed_base = urlparse(base_url)
                    step2_post_url = f"{parsed_base.scheme}://{parsed_base.netloc}{step2_post_url}"
                else:
                    # Relative path
                    login_url_path = action.replace('login-username', 'login')
                    parsed_base = urlparse(base_url)
                    step2_post_url = f"{parsed_base.scheme}://{parsed_base.netloc}/{login_url_path}"
                
                print(f"Form action is {action}, submitting password to: {step2_post_url}")
            else:
                # Use standard URL resolution for the form action
                if action:
                    if action.startswith('http://') or action.startswith('https://'):
                        step2_post_url = action
                    elif action.startswith('//'):
                        # Protocol-relative URL
                        step2_post_url = f"{base_url.split('://')[0]}{action}" if '://' in base_url else f"https:{action}"
                    elif action.startswith('/'):
                        # Absolute path
                        parsed_base = urlparse(base_url)
                        step2_post_url = f"{parsed_base.scheme}://{parsed_base.netloc}{action}"
                    else:
                        # Relative path - resolve relative to current response URL
                        step2_post_url = urljoin(response.url, action)
                else:
                    # No action specified - try /login as default
                    parsed_base = urlparse(base_url)
                    step2_post_url = f"{parsed_base.scheme}://{parsed_base.netloc}/login"
                    print(f"No form action found, using default: {step2_post_url}")
            
            error_details['url'] = step2_post_url
            error_details['login_data_keys'] = list(step2_data.keys())  # For debugging (not passwords)
            
            # Debug: Log what we're submitting (without passwords)
            debug_data = {k: ('[PASSWORD]' if ('password' in k.lower() or (password_field_name and k == password_field_name)) else v) 
                          for k, v in step2_data.items()}
            error_details['submitted_fields'] = debug_data
            print(f"Submitting login data to {step2_post_url}")
            print(f"Fields being submitted: {list(step2_data.keys())}")
            
            # Make sure we preserve cookies and headers for the login POST
            response = self.session.post(step2_post_url, data=step2_data, timeout=10, allow_redirects=True)
            error_details['status_code'] = response.status_code
            error_details['final_url'] = response.url
            
            # Log cookies after login for debugging
            cookie_names = list(self.session.cookies.keys())
            print(f"Cookies after login: {cookie_names}")
            if cookie_names:
                cookie_info = self.get_cookies_info()
                print(f"Cookie details: {cookie_info}")
                # Store cookie info in error_details for debugging
                error_details['cookies_after_login'] = cookie_info
            
            # Make a test request immediately after login to verify session
            if response.status_code in [200, 301, 302, 303, 307, 308]:
                # Try accessing a simple page to establish session
                test_url = response.url if response.url else f'{base_url}/home.php'
                try:
                    test_response = self.session.get(test_url, timeout=5, allow_redirects=True)
                    print(f"Session test after login: Status {test_response.status_code}, URL: {test_response.url}")
                except:
                    pass
            
            # Check if login was successful
            # First check: if we're redirected back to login page with username in query, login likely failed
            if 'login' in response.url.lower():
                # Check if we have username in query params (suggests failed login and redirect back)
                parsed_url = urlparse(response.url)
                if 'username' in parsed_url.query.lower():
                    print(f"Warning: Redirected back to login page with username in query - login may have failed")
                    # Continue checking - might still be logged in but redirected
                # If still on login page without indicators of success, likely failed
                if 'logout' not in response.text.lower()[:1000] and 'dashboard' not in response.text.lower()[:1000]:
                    # Check if there's an error message or if form is still present
                    soup_check = BeautifulSoup(response.text, 'html.parser')
                    login_forms = soup_check.find_all('form', action=lambda x: x and 'login' in str(x).lower() if x else False)
                    if login_forms:
                        error_details['message'] = "Redirected back to login page - login credentials may be invalid or session expired"
                        error_details['redirected_to_login'] = True
                        print(error_details['message'])
                        # Don't return yet - check other indicators first
            
            # Look for redirect to different page (common success indicator)
            final_url_after_login = response.url
            if login_url and login_url.lower() not in response.url.lower():
                # Check if redirect is to a non-login page
                if 'login' not in response.url.lower() and response.status_code in [200, 301, 302, 303, 307, 308]:
                    # URL-encode the redirect URL in case it contains special characters like @
                    parsed = urlparse(final_url_after_login)
                    redirect_url = f"{parsed.scheme}://{parsed.netloc}{quote(parsed.path, safe='/')}"
                    if parsed.query:
                        redirect_url += f"?{quote(parsed.query, safe='=&')}"
                    if parsed.fragment:
                        redirect_url += f"#{quote(parsed.fragment)}"
                    
                    # Try to find alerts page link on this redirected page
                    alerts_link = self.find_alerts_link(response.text, base_url, response.url)
                    if alerts_link:
                        print(f"Found alerts page link on redirect page: {alerts_link}")
                        return True, {'redirect_url': redirect_url, 'alerts_link': alerts_link}
                    
                    print(f"Login successful (redirected to different page: {redirect_url})")
                    return True, {'redirect_url': redirect_url}
            
            # Check for username or common logged-in indicators in response
            if response.status_code == 200:
                response_lower = response.text.lower()
                # Check for username presence or logout link (indicating successful login)
                # Also check for absence of login form (if we're still on login page but logged in)
                has_login_form = 'login' in response.url.lower() or 'form' in response.text.lower()
                has_logout = ('logout' in response_lower or 
                             'sign out' in response_lower or
                             'signout' in response_lower or
                             'log out' in response_lower)
                has_dashboard = 'dashboard' in response_lower
                has_welcome = 'welcome' in response_lower
                has_username = username.lower() in response_lower
                
                if has_logout or has_dashboard or has_welcome or (has_username and not has_login_form):
                    # URL-encode the redirect URL in case it contains special characters like @
                    parsed = urlparse(response.url)
                    redirect_url = f"{parsed.scheme}://{parsed.netloc}{quote(parsed.path, safe='/')}"
                    if parsed.query:
                        redirect_url += f"?{quote(parsed.query, safe='=&')}"
                    if parsed.fragment:
                        redirect_url += f"#{quote(parsed.fragment)}"
                    
                    # Try to find alerts page link on this page
                    alerts_link = self.find_alerts_link(response.text, base_url, response.url)
                    if alerts_link:
                        print(f"Found alerts page link: {alerts_link}")
                        return True, {'redirect_url': redirect_url, 'alerts_link': alerts_link}
                    
                    print(f"Login successful (final URL: {redirect_url})")
                    return True, {'redirect_url': redirect_url}
            
            # Check redirect status codes
            if response.status_code in [301, 302, 303, 307, 308]:
                if 'login' not in response.url.lower():
                    # URL-encode the redirect URL in case it contains special characters like @
                    parsed = urlparse(response.url)
                    redirect_url = f"{parsed.scheme}://{parsed.netloc}{quote(parsed.path, safe='/')}"
                    if parsed.query:
                        redirect_url += f"?{quote(parsed.query, safe='=&')}"
                    if parsed.fragment:
                        redirect_url += f"#{quote(parsed.fragment)}"
                    
                    # Try to find alerts page link on the redirected page
                    alerts_link = self.find_alerts_link(response.text, base_url, response.url)
                    if alerts_link:
                        print(f"Found alerts page link: {alerts_link}")
                        return True, {'redirect_url': redirect_url, 'alerts_link': alerts_link}
                    
                    print(f"Login successful (redirected to: {redirect_url})")
                    return True, {'redirect_url': redirect_url}
            
            # Login appears to have failed - gather detailed error info
            error_text = response.text.lower()
            
            # Check for common error messages
            if 'invalid' in error_text or 'incorrect' in error_text or 'wrong' in error_text:
                error_details['message'] = "Login credentials appear to be invalid"
            elif 'captcha' in error_text or 'recaptcha' in error_text:
                error_details['message'] = "Website may require CAPTCHA verification"
            elif 'session' in error_text or 'timeout' in error_text:
                error_details['message'] = "Session or timeout error"
            elif 'error' in error_text:
                # Try to extract the actual error message
                error_soup = BeautifulSoup(response.text, 'html.parser')
                error_elements = (error_soup.find_all(class_=lambda x: x and 'error' in str(x).lower()) +
                                error_soup.find_all(id=lambda x: x and 'error' in str(x).lower()) +
                                error_soup.find_all('div', {'role': 'alert'}))
                if error_elements:
                    error_msg = error_elements[0].get_text(strip=True)
                    if error_msg:
                        error_details['message'] = f"Error detected: {error_msg[:200]}"
                    else:
                        error_details['message'] = f"Login failed: Status {response.status_code}, redirected to {response.url}"
                else:
                    error_details['message'] = f"Login failed: Status {response.status_code}, redirected to {response.url}"
            else:
                error_details['message'] = f"Login failed: Status {response.status_code}, redirected to {response.url}"
            
            # Save debugging information
            error_details['response_snippet'] = response.text[:1000] if len(response.text) > 1000 else response.text
            
            # Also save the form HTML from step 2 for debugging
            if form:
                error_details['form_html'] = str(form)[:3000] if len(str(form)) > 3000 else str(form)
            
            print(error_details['message'])
            return False, error_details
            
        except requests.RequestException as e:
            error_details['message'] = f"Network error during login: {str(e)}"
            error_details['exception_type'] = type(e).__name__
            print(error_details['message'])
            return False, error_details
        except Exception as e:
            error_details['message'] = f"Unexpected error during login: {str(e)}"
            error_details['exception_type'] = type(e).__name__
            print(error_details['message'])
            return False, error_details
    
    def find_alerts_link(self, html_content, base_url, current_url):
        """
        Find a link to the alerts page on the current page
        
        Args:
            html_content: HTML content of the page
            base_url: Base URL of the site
            current_url: Current page URL for resolving relative links
        
        Returns:
            str: Full URL to alerts page if found, None otherwise
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for links that match the alerts page pattern
            # Common patterns: scba-open-alerts, scba-open-alerts-data, scba/alerts, etc.
            alerts_patterns = [
                'scba-open-alerts',
                'scba-open-alerts-data',
                'scba/alerts',
                'open-alerts',
                'alerts-data'
            ]
            
            # Find all anchor tags
            all_links = soup.find_all('a', href=True)
            
            for link in all_links:
                href = link.get('href', '').strip()
                if not href:
                    continue
                
                # Check if href matches any alerts pattern
                href_lower = href.lower()
                for pattern in alerts_patterns:
                    if pattern in href_lower:
                        # Resolve the URL properly
                        if href.startswith('http://') or href.startswith('https://'):
                            # Absolute URL
                            return href
                        elif href.startswith('//'):
                            # Protocol-relative URL
                            parsed_base = urlparse(base_url)
                            return f"{parsed_base.scheme}:{href}"
                        elif href.startswith('/'):
                            # Absolute path
                            parsed_base = urlparse(base_url)
                            return f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
                        else:
                            # Relative path - resolve relative to current URL
                            return urljoin(current_url, href)
            
            # Also check for links in JavaScript or data attributes
            # Some sites use onclick handlers or data-href attributes
            script_tags = soup.find_all('script')
            for script in script_tags:
                script_text = script.string or ''
                # Look for URLs in script content
                url_pattern = r'["\']([^"\']*scba[^"\']*open[^"\']*alert[^"\']*)["\']'
                matches = re.findall(url_pattern, script_text, re.IGNORECASE)
                for match in matches:
                    if match.startswith('http'):
                        return match
                    elif match.startswith('/'):
                        parsed_base = urlparse(base_url)
                        return f"{parsed_base.scheme}://{parsed_base.netloc}{match}"
            
            return None
        except Exception as e:
            print(f"Error finding alerts link: {e}")
            return None
    
    def verify_session(self, base_url, target_url=None):
        """
        Verify that the session is still valid by checking for authentication
        Optionally verify by accessing the target URL directly
        
        Returns:
            bool: True if session appears valid, False otherwise
        """
        try:
            # If target_url is provided, verify by accessing it directly
            if target_url:
                response = self.session.get(target_url, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    response_lower = response.text.lower()
                    if 'authentication expired' in response_lower or 'session expired' in response_lower:
                        print(f"Session verification failed: Authentication expired when accessing target URL")
                        return False
                    # If we get here and no auth error, session is valid
                    return True
            
            # Otherwise, try accessing a simple page to verify session
            test_url = f'{base_url.rstrip("/")}/home.php'
            response = self.session.get(test_url, timeout=10, allow_redirects=True)
            
            # Check for authentication expired messages
            if response.status_code == 200:
                response_lower = response.text.lower()
                if 'authentication expired' in response_lower or 'session expired' in response_lower:
                    print("Session verification failed: Authentication expired")
                    return False
                # Check if we're redirected to login
                if 'login' in response.url.lower() and 'login' not in test_url.lower():
                    print("Session verification failed: Redirected to login")
                    return False
                return True
            return False
        except Exception as e:
            print(f"Session verification error: {e}")
            return False
    
    def scrape_data(self, base_url='https://pstrax.com', target_url=None, login_redirect_url=None):
        """
        Scrape data from pstrax website after login by sending a POST request to the alerts data endpoint.
        The response should be JSON containing the alerts data.
        
        Args:
            base_url: Base URL of pstrax website
            target_url: Specific URL to scrape (defaults to /scba/scba-open-alerts-data.php?p=home)
            login_redirect_url: URL we were redirected to after login (not used, but kept for compatibility)
        
        Returns:
            dict: Scraped data with JSON response parsed
        """
        try:
            # Construct the alerts data endpoint URL with query parameter
            # Default to scba-open-alerts-data.php?p=home
            if target_url:
                alerts_url = target_url
                # Ensure it has the ?p=home parameter if not present
                if '?p=home' not in alerts_url and '?' not in alerts_url:
                    alerts_url = f"{alerts_url.rstrip('/')}?p=home"
                elif '?p=home' not in alerts_url:
                    # Has query params but not p=home, append it
                    alerts_url = f"{alerts_url}&p=home"
            else:
                # Build default URL
                alerts_url = f'{base_url.rstrip("/")}/scba/scba-open-alerts-data.php?p=home'
            
            print(f"Sending POST request to: {alerts_url}")
            
            # Log cookies before request
            cookies_before = list(self.session.cookies.keys())
            if cookies_before:
                print(f"Cookies being sent: {cookies_before}")
            
            # Prepare form data for the POST request
            form_data = {
                'type': 'all',
                'assignment': 'all',
                'postedby': 'all'
            }
            
            # Set Referer header to the base URL to make request look legitimate
            headers = {
                'Referer': base_url,
                'Accept': 'application/json, text/html, */*',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            # Send POST request to get JSON data
            response = self.session.post(alerts_url, data=form_data, timeout=10, allow_redirects=True, headers=headers)
            
            # Log cookies after request
            cookies_after = list(self.session.cookies.keys())
            if cookies_after != cookies_before:
                new_cookies = set(cookies_after) - set(cookies_before)
                if new_cookies:
                    print(f"New cookies received: {new_cookies}")
            
            # Check response status
            if response.status_code != 200:
                error_msg = f"Failed to access alerts data endpoint. Status: {response.status_code}"
                print(error_msg)
                return {
                    'status': 'error',
                    'error': error_msg,
                    'scraped_at': datetime.utcnow().isoformat(),
                    'url': alerts_url,
                    'status_code': response.status_code
                }
            
            # Check if response indicates authentication expired
            response_text = response.text
            response_lower = response_text.lower()
            if 'authentication expired' in response_lower or 'session expired' in response_lower:
                error_msg = 'Authentication expired - session not maintained'
                print(error_msg)
                return {
                    'status': 'error',
                    'error': error_msg,
                    'scraped_at': datetime.utcnow().isoformat(),
                    'url': alerts_url
                }
            
            # Check if we're redirected to a login page
            if 'login' in response.url.lower():
                error_msg = 'Redirected to login page - session may have expired'
                print(error_msg)
                return {
                    'status': 'error',
                    'error': error_msg,
                    'scraped_at': datetime.utcnow().isoformat(),
                    'url': response.url
                }
            
            # Try to parse JSON response
            # Note: The server may return JSON with Content-Type: text/html, so we parse regardless of header
            json_data = None
            content_type = response.headers.get('Content-Type', 'unknown')
            print(f"Response Content-Type: {content_type}")
            
            # Check if response looks like HTML first (login page)
            if response_text.strip().startswith('<') or '<html' in response_lower:
                soup = BeautifulSoup(response_text, 'html.parser')
                # Check for login forms
                if soup.find('form', action=lambda x: x and 'login' in x.lower() if x else False):
                    error_msg = 'Received HTML login page instead of JSON - session expired'
                    print(error_msg)
                    return {
                        'status': 'error',
                        'error': error_msg,
                        'scraped_at': datetime.utcnow().isoformat(),
                        'url': alerts_url,
                        'response_preview': response_text[:500]
                    }
            
            # Try to parse as JSON regardless of Content-Type header
            try:
                json_data = response.json()
                print(f"Successfully parsed JSON response (Content-Type was {content_type}, but content is JSON)")
                print(f"JSON data size: {len(str(json_data))} characters")
            except (ValueError, json.JSONDecodeError) as e:
                # JSON parsing failed - this might be actual HTML or some other content
                print(f"Failed to parse JSON response: {e}")
                print(f"Response preview (first 500 chars): {response_text[:500]}")
                
                # Check if it looks like valid JSON but just has wrong Content-Type
                # Try parsing the text directly (in case requests library is being strict)
                try:
                    json_data = json.loads(response_text)
                    print(f"Successfully parsed JSON by parsing response.text directly")
                    print(f"JSON data size: {len(str(json_data))} characters")
                except (ValueError, json.JSONDecodeError):
                    # Genuinely not JSON
                    error_msg = f'Expected JSON response but got non-JSON content. Content-Type: {content_type}'
                    print(error_msg)
                    return {
                        'status': 'error',
                        'error': error_msg,
                        'scraped_at': datetime.utcnow().isoformat(),
                        'url': alerts_url,
                        'response_preview': response_text[:500],
                        'content_type': content_type
                    }
            
            # Successfully parsed JSON - return the data
            data = {
                'scraped_at': datetime.utcnow().isoformat(),
                'url': alerts_url,
                'status': 'success',
                'data': json_data  # Store the JSON data directly
            }
            
            print(f"Successfully scraped data from {alerts_url}")
            return data
            
        except requests.RequestException as e:
            error_msg = f"Request error: {str(e)}"
            print(error_msg)
            return {
                'status': 'error',
                'error': error_msg,
                'scraped_at': datetime.utcnow().isoformat(),
                'url': alerts_url if 'alerts_url' in locals() else target_url or 'unknown'
            }
        except Exception as e:
            error_msg = f"Unexpected error during scraping: {str(e)}"
            print(error_msg)
            return {
                'status': 'error',
                'error': error_msg,
                'scraped_at': datetime.utcnow().isoformat(),
                'url': alerts_url if 'alerts_url' in locals() else target_url or 'unknown'
            }


def perform_scrape():
    """Background task to perform scraping"""
    from app import db
    with db.session.no_autoflush:
        config = ScrapeConfig.query.first()
        
        if not config or not config.pstrax_username or not config.pstrax_password_encrypted:
            print("Scraping skipped: No credentials configured")
            return
        
        username = config.pstrax_username
        password = config.get_password()
        
        if not password:
            print("Scraping skipped: Could not decrypt password")
            return
        
        base_url = config.pstrax_base_url or 'https://pstrax.com'
        print(f"Starting scrape for user: {username} at {base_url}")
        
        scraper = PstraxScraper()
        
        # Login
        login_success, login_result = scraper.login(username, password, base_url=base_url)
        if not login_success:
            print("Scraping failed: Login unsuccessful")
            error_data = {
                'status': 'error',
                'error': 'Login failed',
                'scraped_at': datetime.utcnow().isoformat(),
                'error_details': login_result or {}
            }
            scrape_data = ScrapeData()
            scrape_data.set_data(error_data)
            db.session.add(scrape_data)
            config.last_scrape = datetime.utcnow()
            db.session.commit()
            return
        
        # Get target URL from config, or try to find it from the login redirect page
        target_url = None
        
        # First, check if login result contains an alerts link (found on redirect page)
        if login_result and isinstance(login_result, dict):
            alerts_link = login_result.get('alerts_link')
            if alerts_link:
                target_url = alerts_link
                print(f"Using alerts link found on login redirect page: {target_url}")
        
        # If no link found, check config
        if not target_url:
            if hasattr(config, 'scrape_target_url') and config.scrape_target_url:
                target_url = config.scrape_target_url
            else:
                # Default to SCBA alerts data page with ?p=home parameter
                target_url = f'{base_url.rstrip("/")}/scba/scba-open-alerts-data.php?p=home'
        
        # IMPORTANT: Access target URL immediately after login while session is fresh
        # Don't go through intermediate pages (like home.php) that might expire the session
        print(f"Accessing target URL immediately after login: {target_url}")
        
        # Scrape data - go directly to target URL, skipping login redirect URL
        # This prevents session expiration that might occur when accessing intermediate pages
        data = scraper.scrape_data(base_url=base_url, target_url=target_url, login_redirect_url=None)
        
        # Store scraped data
        scrape_data = ScrapeData()
        scrape_data.set_data(data)
        db.session.add(scrape_data)
        
        # Update config
        config.last_scrape = datetime.utcnow()
        db.session.commit()
        
        # Emit update via SocketIO
        emit_scrape_update(data)
        
        print("Scraping completed successfully")

