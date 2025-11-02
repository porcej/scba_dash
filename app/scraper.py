import requests
import json
import re
from urllib.parse import urlparse, urljoin, quote
from bs4 import BeautifulSoup
from datetime import datetime
from app import db
from app.models import ScrapeConfig, ScrapeData
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
            
            # If we're not on login page OR have logout link OR have home button, login likely succeeded
            if is_not_login_page or has_logout_link or has_home_link or has_dashboard:
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
            
            # Uncertain case - not clearly on login page but also no clear success indicators
            # Try to proceed anyway if status is 200
            if response.status_code == 200:
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
    
    def getGearList(self, base_url='https://app1.pstrax.com'):
        """
        Get SCBA gear list data by posting form data to the gear-list endpoint.
        
        Note: The response Content-Type is text/html; charset=UTF-8 but the content is actually JSON.
        
        Args:
            base_url: Base URL of pstrax website (defaults to https://app1.pstrax.com)
        
        Returns:
            requests.Response: The response object from the POST request
        """
        gear_list_url = f'{base_url.rstrip("/")}/scba/gear-list-data.php'
        
        # Prepare form data
        form_data = {
            'limitSearch': '0',
            'btnSubmit': 'Find',
            'typeid': '',
            'statusid': '',
            'sid': ''
        }
        
        # Set headers
        headers = {
            'Referer': base_url,
            'Accept': 'application/json, text/html, */*',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        # Send POST request
        response = self.session.post(gear_list_url, data=form_data, timeout=10, allow_redirects=True, headers=headers)
        
        return response
    
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
            return
        
        # Determine target URL
        target_url = None
        if login_result and isinstance(login_result, dict):
            alerts_link = login_result.get('alerts_link')
            if alerts_link:
                target_url = alerts_link
                print(f"Using alerts link from login: {target_url}")
        
        # Get SCBA alerts using the new method
        print("Fetching SCBA alerts...")
        scba_alerts_response = scraper.getSCBAAlerts(base_url=base_url)
        
        # Prepare data structure
        data = {
            'scraped_at': datetime.utcnow().isoformat(),
            'url': f'{base_url.rstrip("/")}/scba/scba-open-alerts-data.php',
            'status': 'success' if scba_alerts_response.status_code == 200 else 'error'
        }
        
        if scba_alerts_response.status_code == 200:
            try:
                # Try to parse JSON response
                alerts_data = scba_alerts_response.json()
                data['data'] = alerts_data
                print(f"Successfully fetched {len(alerts_data) if isinstance(alerts_data, list) else 'unknown'} alerts")
            except (ValueError, json.JSONDecodeError):
                # If JSON parsing fails, try parsing response.text directly
                try:
                    alerts_data = json.loads(scba_alerts_response.text)
                    data['data'] = alerts_data
                    print(f"Successfully parsed JSON from response.text")
                except (ValueError, json.JSONDecodeError):
                    data['status'] = 'error'
                    data['error'] = 'Failed to parse JSON response'
                    data['response_preview'] = scba_alerts_response.text[:500]
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
        
        # Emit update via SocketIO
        emit_scrape_update(data)
        
        print("Scraping completed successfully")
