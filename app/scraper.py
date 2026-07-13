import requests
import json
import re
from urllib.parse import urlparse, urljoin, quote
from bs4 import BeautifulSoup
from datetime import datetime
from app import db
from sqlalchemy import func, text

from app.models import ScrapeConfig, ScrapeData, Equipment
from app.socketio_events import emit_scrape_update


class PstraxScraper:
    """Web scraper for pstrax website with single-step login"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        self.session.cookies.clear()
    
    def login(self, username, password, base_url='https://pstrax.com'):
        """
        Login to pstrax website using single-step process.
        Login page URL includes username as query parameter.
        
        Args:
            username: Username for login
            password: Password for login
            base_url: Base URL of pstrax website
        
        Returns:
            tuple: (bool: success, dict: result/error_details)
        """
        error_details = {
            'step': None,
            'status_code': None,
            'message': None,
            'url': None
        }
        
        try:
            # Access login page with username in URL
            error_details['step'] = 'accessing_login_page'
            url_escaped_username = quote(username)
            login_url = f'{base_url.rstrip("/")}/login.php?username={url_escaped_username}'
            
            response = self.session.get(login_url, timeout=10)
            
            if response.status_code != 200:
                error_details['message'] = f"Failed to access login page: Status {response.status_code}"
                error_details['status_code'] = response.status_code
                return False, error_details
            
            # Parse login form
            soup = BeautifulSoup(response.text, 'html.parser')
            form = soup.find('form', {'id': 'loginForm'}) or soup.find('form')
            
            if not form:
                error_details['step'] = 'finding_form'
                error_details['message'] = "Login form not found"
                return False, error_details
            
            # Find username field (id='txtuser_name', name='txtuser_name')
            username_field = (soup.find('input', {'id': 'txtuser_name', 'name': 'txtuser_name'}) or
                            soup.find('input', {'id': 'txtuser_name'}) or
                            soup.find('input', {'name': 'txtuser_name'}))
            
            if not username_field:
                error_details['step'] = 'finding_username_field'
                error_details['message'] = "Username field not found"
                return False, error_details
            
            username_value = username_field.get('value', '') or username
            
            # Find password field (id='txtpassword')
            password_field = soup.find('input', {'id': 'txtpassword'}) or soup.find('input', {'type': 'password'})
            
            if not password_field:
                error_details['step'] = 'finding_password_field'
                error_details['message'] = "Password field not found"
                return False, error_details
            
            password_field_name = password_field.get('name') or 'txtpassword'
            
            # Find CSRF token field (name='_token', id='csrf_token')
            csrf_field = (soup.find('input', {'name': '_token', 'id': 'csrf_token'}) or
                         soup.find('input', {'name': '_token'}) or
                         soup.find('input', {'id': 'csrf_token'}))
            
            if not csrf_field:
                error_details['step'] = 'finding_csrf_token'
                error_details['message'] = "CSRF token field not found"
                return False, error_details
            
            csrf_token = csrf_field.get('value', '')
            if not csrf_token:
                error_details['step'] = 'getting_csrf_token'
                error_details['message'] = "CSRF token value is empty"
                return False, error_details
            
            # Prepare login data
            login_data = {
                'txtuser_name': username_value,
                password_field_name: password,
                '_token': csrf_token
            }
            
            # Include all hidden fields (username might be in a hidden field)
            for hidden in form.find_all('input', type='hidden'):
                name = hidden.get('name')
                if name and name not in login_data:
                    login_data[name] = hidden.get('value', '')
            
            # Submit login
            error_details['step'] = 'submitting_login'
            action = form.get('action', '')
            
            if action:
                if action.startswith('http'):
                    login_post_url = action
                elif action.startswith('/'):
                    parsed_base = urlparse(base_url)
                    login_post_url = f"{parsed_base.scheme}://{parsed_base.netloc}{action}"
                else:
                    login_post_url = urljoin(base_url, action)
            else:
                # Default to /login if no action specified
                parsed_base = urlparse(base_url)
                login_post_url = f"{parsed_base.scheme}://{parsed_base.netloc}/login"
            
            error_details['url'] = login_post_url
            response = self.session.post(login_post_url, data=login_data, timeout=10, allow_redirects=True)
            error_details['status_code'] = response.status_code
            
            # Check if login was successful
            soup = BeautifulSoup(response.text, 'html.parser')
            response_lower = response.text.lower()
            response_url_lower = response.url.lower()
            
            # Check multiple indicators of successful login
            is_not_login_page = 'login' not in response_url_lower
            has_logout_link = 'logout' in response_lower or soup.find('a', href=lambda x: x and 'logout' in x.lower() if x else False)
            has_home_link = soup.find(id='homeLinkButton') is not None
            has_dashboard = 'dashboard' in response_lower
            has_username = username.lower() in response_lower
            page_title = (soup.title.string or '').strip().lower() if soup.title and soup.title.string else ''
            has_login_form = (
                soup.find('form', {'id': 'loginForm'}) is not None
                or soup.find('input', {'id': 'txtpassword'}) is not None
                or soup.find('input', {'name': 'txtuser_name'}) is not None
            )
            looks_like_login_page = (
                has_login_form
                or 'pstrax - login' in page_title
                or 'login.php' in response_url_lower
            )
            
            # Do not treat "URL does not contain login" as success by itself.
            # Some PSTrax login pages can still load at non-login-looking URLs.
            has_positive_success_signal = bool(has_logout_link or has_home_link or has_dashboard)
            if has_positive_success_signal and not looks_like_login_page:
                # Try to find alerts link
                alerts_link = self._find_alerts_link(response.text, base_url, response.url)
                result = {'redirect_url': response.url}
                if alerts_link:
                    result['alerts_link'] = alerts_link
                print(f"Login successful - URL: {response.url}, Indicators: not_login_page={is_not_login_page}, logout_link={has_logout_link}, home_link={has_home_link}")
                return True, result
            
            # Check if we're definitely still on login page (more strict check)
            login_form_present = soup.find('form', {'id': 'loginForm'}) is not None or soup.find('form', action=lambda x: x and 'login' in str(x).lower() if x else False)
            if login_form_present and 'login' in response_url_lower:
                error_details['message'] = f"Login failed - still on login page (Status: {response.status_code}, URL: {response.url})"
                error_details['response_preview'] = response.text[:500]
                return False, error_details
            
            # Uncertain case - status 200, page does not look like login.
            # Proceed, but only when we don't detect login markers.
            if response.status_code == 200:
                if looks_like_login_page:
                    error_details['step'] = 'login_verification'
                    error_details['message'] = "Login failed - response still looks like login page"
                    error_details['response_preview'] = response.text[:500]
                    return False, error_details
                print(f"Uncertain login status - proceeding with status 200, URL: {response.url}")
                alerts_link = self._find_alerts_link(response.text, base_url, response.url)
                result = {'redirect_url': response.url}
                if alerts_link:
                    result['alerts_link'] = alerts_link
                return True, result
            
            # Login failed
            error_details['message'] = f"Login failed - Status: {response.status_code}, URL: {response.url}"
            error_details['response_preview'] = response.text[:500]
            return False, error_details
            
        except requests.RequestException as e:
            error_details['message'] = f"Network error: {str(e)}"
            return False, error_details
        except Exception as e:
            error_details['message'] = f"Unexpected error: {str(e)}"
            return False, error_details
    
    def getSCBAAlerts(self, base_url='https://app1.pstrax.com'):
        """
        Get SCBA alerts data by posting form data to the alerts endpoint.
        
        Args:
            base_url: Base URL of pstrax website (defaults to https://app1.pstrax.com)
        
        Returns:
            requests.Response: The response object from the POST request
        """
        alerts_url = f'{base_url.rstrip("/")}/scba/scba-open-alerts-data.php'
        
        # Prepare form data
        form_data = {
            'btnSubmit': 'true',
            'type': 'all',
            'assignment': 'all',
            'postedby': 'all'
        }
        
        # Set headers
        headers = {
            'Referer': base_url,
            'Accept': 'application/json, text/html, */*',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        # Send POST request
        response = self.session.post(alerts_url, data=form_data, timeout=10, allow_redirects=True, headers=headers)
        
        return response
    
    def getGearList(self, base_url='https://app1.pstrax.com', typeid=''):
        """
        Get SCBA gear list data by posting form data to the gear-list endpoint.
        
        Note: The response Content-Type is text/html; charset=UTF-8 but the content is actually JSON.
        
        Args:
            base_url: Base URL of pstrax website (defaults to https://app1.pstrax.com)
        
        Returns:
            requests.Response: The response object from the POST request
        """
        gear_list_url = f'{base_url.rstrip("/")}/scba/gear-list-data.php'
        
        # Request SCBA gear list. Empty typeid requests all available gear types.
        form_data = {
            'limitSearch': '0',
            'btnSubmit': 'Find',
            'typeid': str(typeid) if typeid is not None else '',
            'statusid': '',
            'sid': ''
        }
        headers = {
            'Referer': base_url.rstrip('/') + '/',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        }
        response = self.session.post(
            gear_list_url, data=form_data, timeout=120, allow_redirects=True, headers=headers
        )
        
        return response

    def post_batch_air_fill(self, gear_ids, fill_site_name, base_url='https://app1.pstrax.com'):
        """
        Log a batch cylinder air fill in PSTrax.

        Flow:
        1) POST selected gear ids to modal-add-airFill-batch-log.php
        2) GET/parse the batch fill form HTML
        3) Set fill location, backdate, and chkcontroller_1 checkboxes
        4) POST completed form to post-modal-add-airfill-batch-log.php
        """
        if not gear_ids:
            return {'success': False, 'error': 'No gear IDs provided'}

        base = (base_url or 'https://app1.pstrax.com').rstrip('/')
        modal_url = f'{base}/scba/modal-add-airFill-batch-log.php'
        submit_url = f'{base}/scba/post-modal-add-airfill-batch-log.php'
        fill_site_name = (fill_site_name or '').strip()
        if not fill_site_name:
            return {'success': False, 'error': 'Fill site name is required'}

        headers = {
            'Referer': base + '/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        }

        id_pairs = [('id[]', str(gid)) for gid in gear_ids if gid is not None]
        if not id_pairs:
            return {'success': False, 'error': 'No valid gear IDs provided'}

        try:
            post_modal_resp = self.session.post(
                modal_url, data=id_pairs, timeout=60, allow_redirects=True, headers=headers
            )
        except requests.RequestException as e:
            return {'success': False, 'error': f'Failed posting gear IDs to PSTrax modal: {e}'}

        if post_modal_resp.status_code != 200:
            return {
                'success': False,
                'error': f'PSTrax modal POST returned HTTP {post_modal_resp.status_code}',
            }
        if 'login' in (post_modal_resp.url or '').lower() or 'pstrax - login' in (post_modal_resp.text or '').lower():
            return {'success': False, 'error': 'PSTrax session expired during air-fill modal POST'}

        try:
            get_modal_resp = self.session.get(
                modal_url, timeout=60, allow_redirects=True, headers={
                    'Referer': base + '/',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                }
            )
        except requests.RequestException as e:
            return {'success': False, 'error': f'Failed loading PSTrax air-fill modal: {e}'}

        html = get_modal_resp.text if get_modal_resp.status_code == 200 else ''
        soup = BeautifulSoup(html or '', 'html.parser')
        form = soup.find('form', {'id': 'batchFillForm'}) or soup.find('form', {'name': 'frmLogApp'})

        # Prefer GET HTML; fall back to POST response if GET did not include the form/ids.
        if not form or not form.find('input', {'name': 'id[]'}):
            soup = BeautifulSoup(post_modal_resp.text or '', 'html.parser')
            form = soup.find('form', {'id': 'batchFillForm'}) or soup.find('form', {'name': 'frmLogApp'})

        if not form:
            return {'success': False, 'error': 'PSTrax batch fill form not found in modal response'}

        now_local = datetime.now()
        backdate = now_local.strftime('%m/%d/%Y')
        posted_dt = now_local.strftime('%Y-%m-%d %H:%M:%S')
        backtime = now_local.strftime('%H:%M')

        location_select = (
            form.find('select', {'id': 'notes_464998'})
            or form.find('select', {'name': 'Comments_464998_0'})
        )
        if location_select is None:
            return {'success': False, 'error': 'Fill location select (notes_464998) not found'}

        option_values = [
            (opt.get('value') or '').strip()
            for opt in location_select.find_all('option')
            if (opt.get('value') or '').strip()
        ]
        matched_site = None
        for value in option_values:
            if value.lower() == fill_site_name.lower():
                matched_site = value
                break
        if matched_site is None:
            return {
                'success': False,
                'error': (
                    f'Fill site "{fill_site_name}" not found in PSTrax location options: '
                    f'{", ".join(option_values) if option_values else "(none)"}'
                ),
            }

        # Mark selected option in parsed HTML (also set explicitly when building payload).
        for opt in location_select.find_all('option'):
            if (opt.get('value') or '').strip() == matched_site:
                opt['selected'] = 'selected'
            elif opt.has_attr('selected'):
                del opt['selected']

        backdate_input = form.find('input', {'name': 'backdate'})
        if backdate_input is not None:
            backdate_input['value'] = backdate

        for name, value in (
            ('txtposteddatetime', posted_dt),
            ('backtime', backtime),
        ):
            hidden = form.find('input', {'name': name})
            if hidden is not None:
                hidden['value'] = value

        for chk in form.select('input.chkcontroller_1[type="checkbox"]'):
            chk['checked'] = 'checked'

        payload = []
        seen_names = set()

        def append_field(name, value):
            if not name:
                return
            payload.append((name, '' if value is None else str(value)))
            seen_names.add(name)

        # Preserve existing hidden id[] values if present; otherwise use requested gear ids.
        existing_ids = [inp.get('value') for inp in form.find_all('input', {'name': 'id[]'})]
        if existing_ids:
            for gid in existing_ids:
                if gid is not None and str(gid).strip():
                    append_field('id[]', str(gid).strip())
        else:
            for name, value in id_pairs:
                append_field(name, value)

        for el in form.find_all(['input', 'select', 'textarea']):
            name = el.get('name')
            if not name or name == 'id[]':
                continue

            tag = el.name.lower()
            if tag == 'input':
                itype = (el.get('type') or 'text').lower()
                if itype in ('button', 'submit', 'image', 'reset', 'file'):
                    # Keep explicit submit markers used by PSTrax.
                    if name in ('btnsubmit',) or itype == 'submit':
                        append_field(name, el.get('value') or 'LOG EVENT')
                    continue
                if itype in ('checkbox', 'radio'):
                    classes = el.get('class') or []
                    is_checked = el.has_attr('checked') or 'chkcontroller_1' in classes
                    if is_checked:
                        append_field(name, el.get('value') or 'on')
                    continue
                value = el.get('value') or ''
                if name == 'backdate':
                    value = backdate
                elif name == 'txtposteddatetime':
                    value = posted_dt
                elif name == 'backtime':
                    value = backtime
                append_field(name, value)
            elif tag == 'select':
                if el.get('id') == 'notes_464998' or name == 'Comments_464998_0':
                    append_field(name, matched_site)
                    continue
                selected = el.find('option', selected=True)
                if selected is None:
                    selected = el.find('option')
                append_field(name, selected.get('value') if selected else '')
            elif tag == 'textarea':
                append_field(name, el.get_text() or el.get('value') or '')

        # Ensure required fields exist even if missing from parsed markup.
        if 'backdate' not in seen_names:
            append_field('backdate', backdate)
        if 'Comments_464998_0' not in seen_names:
            append_field('Comments_464998_0', matched_site)
        if 'btnsubmit' not in seen_names:
            append_field('btnsubmit', 'LOG EVENT')

        csrf_token = None
        csrf_input = form.find('input', {'name': '_token'}) or form.find('input', {'id': 'csrf_token'})
        if csrf_input is not None:
            csrf_token = csrf_input.get('value')
        submit_headers = {
            'Referer': modal_url,
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest',
        }
        if csrf_token:
            submit_headers['X-CSRF-TOKEN'] = csrf_token

        try:
            submit_resp = self.session.post(
                submit_url,
                data=payload,
                timeout=60,
                allow_redirects=True,
                headers=submit_headers,
            )
        except requests.RequestException as e:
            return {'success': False, 'error': f'Failed submitting PSTrax air-fill form: {e}'}

        if submit_resp.status_code != 200:
            return {
                'success': False,
                'error': f'PSTrax air-fill submit returned HTTP {submit_resp.status_code}',
                'response_preview': (submit_resp.text or '')[:500],
            }
        if 'login' in (submit_resp.url or '').lower() or 'pstrax - login' in (submit_resp.text or '').lower():
            return {'success': False, 'error': 'PSTrax session expired during air-fill submit'}

        parsed = None
        try:
            parsed = submit_resp.json()
        except (ValueError, json.JSONDecodeError):
            try:
                parsed = json.loads(submit_resp.text)
            except (ValueError, json.JSONDecodeError):
                parsed = None

        if isinstance(parsed, dict):
            status = parsed.get('status')
            result = None
            data = parsed.get('data')
            if isinstance(data, dict):
                result = data.get('result')
            if status in (200, '200') or (isinstance(result, str) and result.lower() == 'logged'):
                return {
                    'success': True,
                    'fill_site': matched_site,
                    'gear_ids': [str(g) for g in gear_ids],
                    'response': parsed,
                }
            return {
                'success': False,
                'error': f'PSTrax air-fill submit returned unexpected payload: {parsed}',
            }

        # Some PSTrax installs return non-JSON success bodies.
        body = (submit_resp.text or '').lower()
        if 'logged' in body or 'success' in body:
            return {
                'success': True,
                'fill_site': matched_site,
                'gear_ids': [str(g) for g in gear_ids],
                'response_preview': (submit_resp.text or '')[:300],
            }

        return {
            'success': False,
            'error': 'PSTrax air-fill submit did not return a recognizable success response',
            'response_preview': (submit_resp.text or '')[:500],
        }
    
    def _find_alerts_link(self, html_content, base_url, current_url):
        """Find alerts page link in HTML content"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for links matching alerts patterns
            for link in soup.find_all('a', href=True):
                href = link.get('href', '').lower()
                if 'scba-open-alerts' in href or 'scba/alerts' in href:
                    full_url = link.get('href')
                    if full_url.startswith('http'):
                        return full_url
                    elif full_url.startswith('/'):
                        parsed = urlparse(base_url)
                        return f"{parsed.scheme}://{parsed.netloc}{full_url}"
                    else:
                        return urljoin(current_url, full_url)
            return None
        except Exception as e:
            print(f"Error finding alerts link: {e}")
            return None
    
    def scrape_data(self, base_url='https://pstrax.com', target_url=None, login_redirect_url=None):
        """
        Scrape alerts data by sending POST request to alerts endpoint.
        Response should be JSON (even if Content-Type says text/html).
        
        Args:
            base_url: Base URL of pstrax website
            target_url: Specific URL to scrape (defaults to /scba/scba-open-alerts-data.php?p=home)
            login_redirect_url: Not used, kept for compatibility
        
        Returns:
            dict: Scraped data with JSON response
        """
        try:
            # Build alerts URL
            if target_url:
                alerts_url = target_url
                if '?p=home' not in alerts_url:
                    if '?' in alerts_url:
                        alerts_url = f"{alerts_url}&p=home"
                    else:
                        alerts_url = f"{alerts_url}?p=home"
            else:
                alerts_url = f'{base_url.rstrip("/")}/scba/scba-open-alerts-data.php?p=home'
            
            print(f"Sending POST request to: {alerts_url}")
            
            # Prepare form data
            form_data = {
                'type': 'all',
                'assignment': 'all',
                'postedby': 'all'
            }
            
            # Set headers
            headers = {
                'Referer': base_url,
                'Accept': 'application/json, text/html, */*',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            # Send POST request
            response = self.session.post(alerts_url, data=form_data, timeout=10, allow_redirects=True, headers=headers)
            
            # Check response status
            if response.status_code != 200:
                return {
                    'status': 'error',
                    'error': f"Failed to access alerts endpoint. Status: {response.status_code}",
                    'scraped_at': datetime.utcnow().isoformat(),
                    'url': alerts_url,
                    'status_code': response.status_code
                }
            
            # Check for authentication errors
            response_text = response.text
            response_lower = response_text.lower()
            
            if 'authentication expired' in response_lower or 'session expired' in response_lower:
                return {
                    'status': 'error',
                    'error': 'Authentication expired',
                    'scraped_at': datetime.utcnow().isoformat(),
                    'url': alerts_url
                }
            
            if 'login' in response.url.lower():
                return {
                    'status': 'error',
                    'error': 'Redirected to login page',
                    'scraped_at': datetime.utcnow().isoformat(),
                    'url': response.url
                }
            
            # Try to parse JSON (ignore Content-Type header)
            try:
                # First try response.json()
                json_data = response.json()
            except (ValueError, json.JSONDecodeError):
                # If that fails, try parsing response.text directly
                try:
                    json_data = json.loads(response_text)
                except (ValueError, json.JSONDecodeError):
                    # Check if it's actually HTML (login page)
                    if response_text.strip().startswith('<') or '<html' in response_lower:
                        soup = BeautifulSoup(response_text, 'html.parser')
                        if soup.find('form', action=lambda x: x and 'login' in str(x).lower() if x else False):
                            return {
                                'status': 'error',
                                'error': 'Received HTML login page instead of JSON',
                                'scraped_at': datetime.utcnow().isoformat(),
                                'url': alerts_url
                            }
                    
                    # Not JSON and not HTML login page
                    return {
                        'status': 'error',
                        'error': f'Expected JSON but got non-JSON content. Content-Type: {response.headers.get("Content-Type", "unknown")}',
                        'scraped_at': datetime.utcnow().isoformat(),
                        'url': alerts_url,
                        'response_preview': response_text[:500]
                    }
            
            # Successfully parsed JSON
            return {
                'scraped_at': datetime.utcnow().isoformat(),
                'url': alerts_url,
                'status': 'success',
                'data': json_data
            }
            
        except requests.RequestException as e:
            return {
                'status': 'error',
                'error': f"Request error: {str(e)}",
                'scraped_at': datetime.utcnow().isoformat(),
                'url': alerts_url if 'alerts_url' in locals() else target_url or 'unknown'
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': f"Unexpected error: {str(e)}",
                'scraped_at': datetime.utcnow().isoformat(),
                'url': alerts_url if 'alerts_url' in locals() else target_url or 'unknown'
            }


def _prune_scrape_data_keep_latest(db):
    """
    Keep only the newest scrape_data row (highest id). SQLite grows quickly if
    every scrape appends forever. Run VACUUM only when deleting many rows at
    once (e.g. first cleanup of a huge history), not on every routine 1-row delete.
    """
    count = ScrapeData.query.count()
    if count <= 1:
        return
    latest_id = db.session.query(func.max(ScrapeData.id)).scalar()
    if latest_id is None:
        return
    deleted = ScrapeData.query.filter(ScrapeData.id != latest_id).delete(
        synchronize_session=False
    )
    db.session.commit()
    if deleted >= 100:
        try:
            with db.engine.connect() as conn:
                conn.execute(text("VACUUM"))
                conn.commit()
        except Exception as e:
            print(f"VACUUM after scrape_data prune skipped: {e}")


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
            print(f"***********************************************************************")
            print(f"********************************************************************")
            print(f"********************************************************************")
            print(error_data)
            print(f"********************************************************************")
            print(f"********************************************************************")
            scba_alerts = scraper.getSCBAAlerts(base_url=base_url)
            if scba_alerts.status_code != 200:
                error_data['error'] = 'Failed to get SCBA alerts'
                error_data['error_details'] = scba_alerts.text
            else:
                error_data['error'] = 'Successfully got SCBA alerts'
                error_data['error_details'] = scba_alerts.json()
            scrape_data = ScrapeData()
            scrape_data.set_data(error_data)
            db.session.add(scrape_data)
            config.last_scrape = datetime.utcnow()
            db.session.commit()
            _prune_scrape_data_keep_latest(db)
            return
        
        # Determine target URL
        target_url = None
        if login_result and isinstance(login_result, dict):
            alerts_link = login_result.get('alerts_link')
            if alerts_link:
                target_url = alerts_link
                print(f"Using alerts link from login: {target_url}")
        
        print("Fetching SCBA alerts...")
        scba_alerts_response = scraper.getSCBAAlerts(base_url=base_url)

        data = {
            'scraped_at': datetime.utcnow().isoformat(),
            'url': f'{base_url.rstrip("/")}/scba/scba-open-alerts-data.php',
            'status': 'success' if scba_alerts_response.status_code == 200 else 'error'
        }

        if scba_alerts_response.status_code == 200:
            try:
                alerts_data = scba_alerts_response.json()
                data['data'] = alerts_data
                print(f"Successfully fetched {len(alerts_data) if isinstance(alerts_data, list) else 'unknown'} alerts")
            except (ValueError, json.JSONDecodeError):
                try:
                    alerts_data = json.loads(scba_alerts_response.text)
                    data['data'] = alerts_data
                    print("Successfully parsed JSON from response.text")
                except (ValueError, json.JSONDecodeError):
                    data['status'] = 'error'
                    data['error'] = 'Failed to parse JSON response'
                    data['response_preview'] = scba_alerts_response.text[:500]
                    data['response_content_type'] = scba_alerts_response.headers.get('Content-Type', 'unknown')
                    data['response_url'] = scba_alerts_response.url
                    lower_body = scba_alerts_response.text.lower()
                    if '<title>pstrax - login' in lower_body or 'loginform' in lower_body:
                        data['error'] = 'Authentication appears to have failed (received PSTrax login page)'
        else:
            data['error'] = f"Failed to fetch SCBA alerts. Status: {scba_alerts_response.status_code}"
            data['status_code'] = scba_alerts_response.status_code
            if 'login' in scba_alerts_response.url.lower():
                data['error'] = 'Authentication expired - redirected to login'

        # Store scraped data
        scrape_data = ScrapeData()
        scrape_data.set_data(data)
        db.session.add(scrape_data)
        
        # Update config
        config.last_scrape = datetime.utcnow()
        db.session.commit()

        _prune_scrape_data_keep_latest(db)

        emit_scrape_update(data)
        if data.get('status') == 'success':
            print("Scraping completed successfully")
        else:
            print(f"Scraping completed with errors: {data.get('error')}")


def perform_equipment_scrape():
    """Fetch PSTrax equipment (all types) and replace the equipment table."""
    from app import db

    with db.session.no_autoflush:
        config = ScrapeConfig.query.first()
        if not config or not config.pstrax_username or not config.pstrax_password_encrypted:
            print("Equipment scrape skipped: No credentials configured")
            return
        password = config.get_password()
        if not password:
            print("Equipment scrape skipped: Could not decrypt password")
            return

        base_url = config.pstrax_base_url or 'https://pstrax.com'
        print(f"Starting equipment scrape at {base_url}")

        scraper = PstraxScraper()
        login_success, login_result = scraper.login(
            config.pstrax_username, password, base_url=base_url
        )
        if not login_success:
            print(f"Equipment scrape failed: login unsuccessful — {login_result}")
            return

        resp = scraper.getGearList(base_url=base_url, typeid='')
        if resp.status_code != 200:
            print(f"Equipment scrape failed: HTTP {resp.status_code}")
            return
        if 'login' in (resp.url or '').lower():
            print("Equipment scrape failed: session redirected to login")
            return

        try:
            payload = resp.json()
        except (ValueError, json.JSONDecodeError):
            try:
                payload = json.loads(resp.text)
            except (ValueError, json.JSONDecodeError) as e:
                print(f"Equipment scrape failed: invalid JSON ({e})")
                return

        rows = payload.get('data') if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            print("Equipment scrape failed: response missing data array")
            return

        now = datetime.utcnow()
        try:
            Equipment.query.delete(synchronize_session=False)
            for item in rows:
                try:
                    db.session.add(Equipment.from_pstrax_row(item, now))
                except (ValueError, TypeError, KeyError) as ex:
                    print(f"Equipment scrape: skip row {item.get('gearid')}: {ex}")
            config.last_equipment_scrape = now
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Equipment scrape failed storing rows: {e}")
            return

        print(f"Equipment scrape completed: {len(rows)} rows stored")
        from app.socketio_events import emit_equipment_updated
        emit_equipment_updated()


def perform_pstrax_batch_air_fill(gear_ids, fill_site_name):
    """Login to PSTrax and submit a batch air-fill log for the given gear IDs."""
    config = ScrapeConfig.query.first()
    if not config or not config.pstrax_username or not config.pstrax_password_encrypted:
        return {'success': False, 'error': 'PSTrax credentials are not configured'}

    password = config.get_password()
    if not password:
        return {'success': False, 'error': 'Could not decrypt PSTrax password'}

    base_url = config.pstrax_base_url or 'https://app1.pstrax.com'
    scraper = PstraxScraper()
    login_success, login_result = scraper.login(
        config.pstrax_username, password, base_url=base_url
    )
    if not login_success:
        return {
            'success': False,
            'error': 'PSTrax login failed',
            'details': login_result or {},
        }

    result = scraper.post_batch_air_fill(
        gear_ids=gear_ids,
        fill_site_name=fill_site_name,
        base_url=base_url,
    )
    if result.get('success'):
        print(
            f"PSTrax batch air fill logged for site={fill_site_name} "
            f"gear_ids={list(gear_ids)}"
        )
    else:
        print(f"PSTrax batch air fill failed: {result.get('error')}")
    return result
