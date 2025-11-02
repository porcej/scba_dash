# Scraper Troubleshooting Guide

If you're experiencing "Login failed" errors, follow these troubleshooting steps:

## 1. Check Error Details

After a failed scrape, check the dashboard's "Scraped Data" section. The error data will include detailed information:
- `step`: Which step of the login process failed
- `status_code`: HTTP status code received
- `message`: Detailed error message
- `url`: URL that was accessed
- `error_details`: Additional debugging information

## 2. Common Issues and Solutions

### Issue: "Failed to access login page"
**Possible causes:**
- Incorrect base URL (currently set to `https://pstrax.com`)
- Website is down or unreachable
- Firewall/network blocking the request

**Solution:** 
- Verify the correct URL for the pstrax website
- Update the `base_url` parameter in `app/scraper.py` if needed

### Issue: "Login form not found"
**Possible causes:**
- Website structure has changed
- Form uses JavaScript rendering (requires Selenium instead of requests)

**Solution:**
- Inspect the actual login page HTML
- Update form selectors in `app/scraper.py` (line 56)
- Consider using Selenium for JavaScript-heavy sites

### Issue: "Could not find username/password fields"
**Possible causes:**
- Form uses non-standard field names
- Fields are in a different form or container

**Solution:**
- Check the `error_details['inputs_found']` in the error data
- Update the `possible_username_fields` list (line 69) with the correct field name
- Update the password field selector if needed (line 83)

### Issue: "Login credentials appear to be invalid"
**Possible causes:**
- Wrong username or password
- Password encryption/encoding issues
- Account locked or requires additional verification

**Solution:**
- Double-check credentials in Settings
- Try logging in manually through a browser to verify credentials work
- Check if the account requires two-factor authentication

### Issue: "Website may require CAPTCHA verification"
**Possible causes:**
- The website uses CAPTCHA/recaptcha for bot protection

**Solution:**
- Manual intervention required - scrapers cannot bypass CAPTCHA
- Consider using a service that provides CAPTCHA solving (not recommended for production)
- Contact website administrator for API access if available

## 3. Customizing the Scraper

The scraper in `app/scraper.py` is a template that needs customization for your specific pstrax website.

### Steps to Customize:

1. **Identify the Login URL:**
   ```python
   login_url = f'{base_url}/login'  # Line 39 - update if different
   ```

2. **Identify Form Field Names:**
   - Open the pstrax login page in browser
   - Inspect the HTML form
   - Find the `name` or `id` attributes of username and password fields
   - Update `possible_username_fields` list (line 69)

3. **Identify Form Action:**
   - Check the form's `action` attribute
   - Verify the login POST endpoint

4. **Identify Success Indicators:**
   - Determine how to detect successful login:
     - Redirect URL pattern?
     - Presence of specific text on page?
     - Status code?
   - Update the success checks (lines 120-127)

5. **Test Login Manually:**
   ```python
   # You can test login outside the app:
   from app.scraper import PstraxScraper
   scraper = PstraxScraper()
   success, error = scraper.login('your_username', 'your_password')
   print(f"Success: {success}, Error: {error}")
   ```

## 4. Debug Mode

Check the server console/logs when triggering a scrape. The scraper prints detailed information about each step.

## 5. Alternative Approaches

If the website is too complex for `requests` + `BeautifulSoup`:

- **Selenium**: For JavaScript-rendered pages
- **API Access**: Check if pstrax offers an API
- **Cookie-based Authentication**: If you can export cookies from browser

## Need More Help?

Check the error_details in the scraped data JSON on the dashboard for specific information about what failed.

