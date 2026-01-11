"""
Mobile API for CRM Task Management.
Provides REST endpoints for CRUD operations, filtering, and specialized views.

Most endpoints require authentication via Frappe session or OAuth token.
The `get_oauth_config` endpoint allows guest access for retrieving site-specific OAuth settings.
"""

import frappe
import os
from frappe import _
from frappe.utils import today, getdate, nowdate, cint, strip_html, add_days
from frappe.desk.form.assign_to import add as assign_task, remove as unassign_task


def _safe_fields(dt, want):
	"""
	Return only fields that exist on the given doctype.
	Prevents KeyErrors when querying fields that don't exist.
	"""
	meta = frappe.get_meta(dt)
	have = {f.fieldname for f in meta.fields}
	# standard meta fields we may use:
	have |= {"name", "modified"}
	return [f for f in want if f in have]


def _get_assigned_users(doctype, docname):
	"""
	Get all assigned users for a document with full user details.
	
	Args:
		doctype: Document type (e.g., "CRM Task")
		docname: Document name/ID
		
	Returns:
		List of user objects with email, name, and profile_pic
	"""
	assigned_users = []
	
	# Return empty list if docname is None or empty
	if not docname:
		return assigned_users
	
	# Get assigned users from ToDo table (Frappe's assign_to system)
	todos = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": doctype,
			"reference_name": docname,
			"status": "Open"
		},
		fields=["allocated_to"],
		distinct=True
	)
	
	# Collect unique user emails
	user_emails = set()
	for todo in todos:
		if todo.get("allocated_to"):
			user_emails.add(todo.get("allocated_to"))
	
	# If no users found in ToDo, check the assigned_to field directly
	# Only if docname is not None
	if not user_emails and docname:
		try:
			task_doc = frappe.get_doc(doctype, docname)
			if hasattr(task_doc, "assigned_to") and task_doc.assigned_to:
				user_emails.add(task_doc.assigned_to)
		except Exception:
			# If document doesn't exist or error occurs, skip
			pass
	
	# Get user details for each assigned user
	for email in user_emails:
		try:
			user = frappe.get_doc("User", email)
			user_data = {
				"email": user.email or email,
				"name": user.full_name or user.name,
			}
			
			# Get profile picture if available
			if hasattr(user, "user_image") and user.user_image:
				user_data["profile_pic"] = user.user_image
			elif hasattr(user, "photo") and user.photo:
				user_data["profile_pic"] = user.photo
			else:
				user_data["profile_pic"] = None
			
			assigned_users.append(user_data)
		except frappe.DoesNotExistError:
			# User doesn't exist, skip
			continue
		except Exception:
			# Error fetching user, skip
			continue
	
	return assigned_users


def _ensure_user_from_mobile_data(email=None, name=None, profile_pic=None, user_id=None):
	"""
	Ensure a user exists from mobile app data.
	Creates or updates user if needed.
	
	Args:
		email: User email (required)
		name: User full name
		profile_pic: Profile picture URL or file path
		user_id: User ID from mobile app
	
	Returns:
		User email (for use in assignments)
	"""
	if not email:
		return None
	
	# Check if user exists
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		updated = False
		
		# Update name if provided
		if name and name != user.full_name:
			user.full_name = name
			updated = True
		
		# Update profile picture if provided
		if profile_pic and profile_pic != getattr(user, "user_image", None):
			if hasattr(user, "user_image"):
				user.user_image = profile_pic
				updated = True
			elif hasattr(user, "photo"):
				user.photo = profile_pic
				updated = True
		
		if updated:
			user.save(ignore_permissions=True)
			frappe.db.commit()
		
		return email
	else:
		# Create new user (if permissions allow)
		try:
			user = frappe.new_doc("User")
			user.email = email
			user.full_name = name or email.split("@")[0]
			user.enabled = 1
			user.send_welcome_email = 0
			
			# Set profile picture if provided
			if profile_pic:
				if hasattr(user, "user_image"):
					user.user_image = profile_pic
				elif hasattr(user, "photo"):
					user.photo = profile_pic
			
			user.insert(ignore_permissions=True)
			frappe.db.commit()
			return email
		except Exception as e:
			frappe.log_error(f"Failed to create user {email}: {str(e)}", "User Creation Error")
			# Return email anyway - assignment will fail gracefully if user doesn't exist
			return email


def get_compact_task(task, return_all_fields=False):
	"""
	Return task representation.
	Accepts both Document objects and dict-like objects (frappe._dict).
	
	Args:
		task: Task document or dict
		return_all_fields: If True, return all available fields from task object
	"""
	# Handle both dict-like and Document objects
	def _get(obj, key, default=None):
		if isinstance(obj, dict):
			return obj.get(key, default)
		return getattr(obj, key, default)
	
	# Get task name/id
	task_name = task.name if hasattr(task, "name") else task.get("name")
	
	# If return_all_fields is True, return all fields from task object
	if return_all_fields:
		result = {}
		# Get all fields from task object
		if isinstance(task, dict):
			# Dict-like object - copy all fields except internal ones
			for key, value in task.items():
				if key not in ['doctype'] and value is not None:
					result[key] = value
			# Clean HTML from description field if it exists
			if 'description' in result and result['description']:
				result['description'] = strip_html(result['description']).strip()
		else:
			# Document object - get all fields from meta
			for field in task.meta.fields:
				fieldname = field.fieldname
				# Skip internal/system fields
				if fieldname in ['doctype']:
					continue
				# Skip child tables (they're handled separately if needed)
				if field.fieldtype == 'Table':
					continue
				# Get field value
				value = getattr(task, fieldname, None)
				# Include field if it has a value or is a standard/important field
				# Always include description even if empty (it's an important field)
				important_fields = ['name', 'modified', 'creation', 'owner', 'modified_by', 'description']
				if value is not None or fieldname in important_fields:
					result[fieldname] = value
			# Ensure standard fields are included
			result['name'] = task.name
			if hasattr(task, 'modified'):
				result['modified'] = task.modified
			if hasattr(task, 'creation'):
				result['creation'] = task.creation
			if hasattr(task, 'owner'):
				result['owner'] = task.owner
			if hasattr(task, 'modified_by'):
				result['modified_by'] = task.modified_by
			
			# Clean HTML from description field if it exists
			if 'description' in result and result['description']:
				result['description'] = strip_html(result['description']).strip()
	else:
		# Compact mode - return only core fields
		result = {
			"name": task_name,
			"title": _get(task, "title") or (_get(task, "description", "")[:50] if _get(task, "description") else ""),
			"status": _get(task, "status"),
			"priority": _get(task, "priority"),
			"start_date": _get(task, "start_date"),
			"modified": _get(task, "modified")
		}
		
		# Add optional fields if they exist
		due_date = _get(task, "due_date")
		if due_date is not None:
			result["due_date"] = due_date
	
	# Get assigned users with full details (always override assigned_to field)
	try:
		assigned_users = _get_assigned_users("CRM Task", task_name)
		if assigned_users:
			result["assigned_to"] = assigned_users
		else:
			# Fallback: check if assigned_to field exists (single user)
			assigned_to = _get(task, "assigned_to")
			if assigned_to:
				# Try to get user details for single assigned user
				try:
					user = frappe.get_doc("User", assigned_to)
					result["assigned_to"] = [{
						"email": user.email or assigned_to,
						"name": user.full_name or user.name,
						"profile_pic": getattr(user, "user_image", None) or getattr(user, "photo", None) or None
					}]
				except Exception:
					# If user doesn't exist or error, return empty array
					result["assigned_to"] = []
			else:
				result["assigned_to"] = []
	except Exception:
		# Error getting assigned users, return empty array
		result["assigned_to"] = []
	
	# Expand link fields to return names instead of IDs
	# Lead field - return lead_name instead of ID
	lead_id = _get(result, "lead")
	if lead_id:
		try:
			lead_doc = frappe.get_doc("CRM Lead", lead_id)
			lead_name = lead_doc.get("lead_name") or lead_doc.get("organization") or lead_doc.get("email") or lead_id
			result["lead"] = lead_name
			result["lead_id"] = lead_id
		except Exception:
			result["lead_id"] = lead_id
	
	# Reference DocName (Lead) - return lead name
	reference_docname = _get(result, "reference_docname")
	reference_doctype = _get(result, "reference_doctype")
	if reference_docname and reference_doctype == "CRM Lead":
		try:
			lead_doc = frappe.get_doc("CRM Lead", reference_docname)
			lead_name = lead_doc.get("lead_name") or lead_doc.get("organization") or lead_doc.get("email") or reference_docname
			result["reference_docname"] = lead_name
			result["reference_docname_id"] = reference_docname
		except Exception:
			result["reference_docname_id"] = reference_docname
	
	# Project field - return project_name instead of ID
	project_id = _get(result, "project")
	if project_id:
		try:
			project_doc = frappe.get_doc("Real Estate Project", project_id)
			project_name = project_doc.get("project_name") or project_id
			result["project"] = project_name
			result["project_id"] = project_id
		except Exception:
			result["project_id"] = project_id
	
	# Unit field - return unit_name instead of ID
	unit_id = _get(result, "unit")
	if unit_id:
		try:
			unit_doc = frappe.get_doc("Unit", unit_id)
			unit_name = unit_doc.get("unit_name") or unit_doc.get("name") or unit_id
			result["unit"] = unit_name
			result["unit_id"] = unit_id
		except Exception:
			result["unit_id"] = unit_id
	
	# Project Unit field - return unit_name instead of ID
	project_unit_id = _get(result, "project_unit")
	if project_unit_id:
		try:
			project_unit_doc = frappe.get_doc("Project Unit", project_unit_id)
			project_unit_name = project_unit_doc.get("unit_name") or project_unit_doc.get("name") or project_unit_id
			result["project_unit"] = project_unit_name
			result["project_unit_id"] = project_unit_id
		except Exception:
			result["project_unit_id"] = project_unit_id
	
	return result


def _validate_host():
	"""
	Validate that the request Host header belongs to the current site's configured domains.
	
	This prevents returning client_id for external domains that don't belong to the site.
	
	Returns:
		None (raises ValidationError if host is not allowed)
	
	Raises:
		frappe.exceptions.ValidationError: If host is not in site's allowed domains
	"""
	# Extract host from request headers
	# Priority: X-Forwarded-Host (if behind proxy) > Host header
	request = frappe.local.request if hasattr(frappe.local, 'request') else None
	if not request:
		frappe.log_error(
			"Request object not available in frappe.local",
			"OAuth Host Validation Error"
		)
		frappe.throw(_(
			"Request information is not available. Please ensure you are accessing a valid Frappe site."
		))
	
	# Get host from headers
	host = None
	if request.headers.get("X-Forwarded-Host"):
		host = request.headers.get("X-Forwarded-Host")
		# X-Forwarded-Host can contain multiple hosts, take the first one
		if "," in host:
			host = host.split(",")[0].strip()
	elif request.headers.get("Host"):
		host = request.headers.get("Host")
	
	if not host:
		frappe.log_error(
			"Host header not found in request",
			"OAuth Host Validation Error"
		)
		frappe.throw(_(
			"Host header is missing. Please ensure you are accessing via a valid domain."
		))
	
	# Normalize host: lowercase, remove port
	host = host.lower().split(":")[0].strip()
	
	# Get site configuration
	site_name = frappe.local.site if frappe.local else None
	if not site_name:
		frappe.log_error(
			"Site name not available for host validation",
			"OAuth Host Validation Error"
		)
		frappe.throw(_(
			"Site information is not available. Please contact system administrator."
		))
	
	# Get allowed domains from site config
	allowed_domains = []
	try:
		site_config = frappe.get_site_config()
		
		# Get domains list if available
		if "domains" in site_config and site_config["domains"]:
			if isinstance(site_config["domains"], list):
				allowed_domains.extend([d.lower().strip() for d in site_config["domains"]])
			elif isinstance(site_config["domains"], str):
				# Comma-separated or space-separated
				domains_str = site_config["domains"]
				allowed_domains.extend([d.lower().strip() for d in domains_str.replace(",", " ").split()])
		
		# Get host_name if available
		if "host_name" in site_config and site_config["host_name"]:
			host_name = site_config["host_name"].lower().strip()
			if host_name not in allowed_domains:
				allowed_domains.append(host_name)
		
		# SECURITY: If no domains configured, use site_name ONLY if it matches host
		# This is a minimal fallback for sites without explicit domain config
		# But we still require exact match - no wildcards, no other domains
		if not allowed_domains:
			site_name_lower = site_name.lower().strip()
			# Only allow if host exactly matches site_name (exact match required)
			if host == site_name_lower:
				allowed_domains.append(site_name_lower)
			else:
				# Host doesn't match site_name and no domains configured - DENY
				frappe.log_error(
					f"OAuth rejected: Site '{site_name}' has no domains config. Host '{host}' != site_name.",
					"OAuth Host Validation"
				)
				frappe.throw(_(
					"Access denied: Domain '{host}' is not configured for site '{site_name}'. "
					"Please configure 'domains' in site_config.json."
				).format(host=host, site_name=site_name))
	except Exception as e:
		# If we can't read config, use site_name as last resort ONLY if it matches host
		site_name_lower = site_name.lower().strip() if site_name else None
		if site_name_lower and host == site_name_lower:
			# Exact match - allow as minimal fallback
			allowed_domains = [site_name_lower]
		else:
			# No match or no site_name - DENY
			frappe.log_error(
				f"OAuth rejected: Config error for '{site_name}'. Host '{host}' not allowed.",
				"OAuth Host Validation"
			)
			frappe.throw(_(
				"Site configuration error. Access denied. Please contact administrator."
			))
	
	# Allow localhost and 127.0.0.1 ONLY if explicitly in allowed_domains
	# Do NOT allow them automatically - this is a security risk
	development_hosts = ["localhost", "127.0.0.1"]
	
	# Check if host is allowed
	host_allowed = False
	if host in allowed_domains:
		host_allowed = True
	elif host in development_hosts and host in allowed_domains:
		# Only allow development hosts if explicitly in allowed_domains
		host_allowed = True
	
	if not host_allowed:
		# Log the rejection for security tracking (short message to avoid truncation)
		frappe.log_error(
			f"OAuth rejected: Host '{host}' not in allowed domains for '{site_name}'.",
			"OAuth Host Validation"
		)
		frappe.throw(_(
			"Access denied: The domain '{host}' is not configured for this site. "
			"Please use a valid domain for site '{site_name}'."
		).format(host=host, site_name=site_name))


def _ensure_mobile_oauth_settings():
	"""
	Ensure Mobile OAuth Settings exist and are configured with a valid client_id.
	
	This function is idempotent:
	- If settings exist and have client_id, returns them unchanged
	- If settings exist but client_id is empty, creates OAuth Client and updates settings
	- If settings don't exist, creates them along with OAuth Client
	
	Returns:
		Mobile OAuth Settings document
	"""
	# Validate that the current site exists in Frappe bench
	# This prevents creating OAuth clients for non-existent sites (e.g., facebook.com)
	site_name = frappe.local.site if frappe.local else None
	if not site_name:
		frappe.log_error(
			"Site name not available in frappe.local",
			"OAuth Auto-Config Error"
		)
		frappe.throw(_(
			"Site information is not available. Please ensure you are accessing a valid Frappe site."
		))
	
	# Check if the site exists in the bench by verifying site directory exists
	# This prevents creating OAuth clients for domains that route to non-existent sites
	# Get bench path from frappe local
	if hasattr(frappe.local, 'site_path') and frappe.local.site_path:
		# site_path is typically: /path/to/bench/sites/site_name
		bench_path = os.path.dirname(os.path.dirname(frappe.local.site_path))
		site_path = frappe.local.site_path
		
		if not os.path.exists(site_path):
			frappe.log_error(
				f"Site '{site_name}' does not exist in Frappe bench. "
				f"Site directory not found at: {site_path}. "
				f"Requested domain may not be configured.",
				"OAuth Auto-Config Error"
			)
			frappe.throw(_(
				"Site '{site_name}' is not configured in this Frappe bench. "
				"Please contact system administrator or use a valid site domain."
			).format(site_name=site_name))
	
	# Additional check: verify database connection is valid
	# This helps catch cases where domain routing is wrong
	try:
		if not hasattr(frappe.conf, 'db_name') or not frappe.conf.db_name:
			frappe.log_error(
				f"Site '{site_name}' database configuration is missing.",
				"OAuth Auto-Config Error"
			)
			frappe.throw(_(
				"Site '{site_name}' is not properly configured. "
				"Database configuration is missing. Please contact system administrator."
			).format(site_name=site_name))
		
		# Test database connection
		frappe.db.sql("SELECT 1", as_dict=True)
	except Exception as db_error:
		frappe.log_error(
			f"Database connection failed for site '{site_name}': {str(db_error)}",
			"OAuth Auto-Config Error"
		)
		frappe.throw(_(
			"Site '{site_name}' is not properly configured. "
			"Database connection failed. Please contact system administrator."
		).format(site_name=site_name))
	
	# First check if the DocType exists in the database
	if not frappe.db.exists("DocType", "Mobile OAuth Settings"):
		frappe.log_error(
			f"Mobile OAuth Settings DocType not found on site '{site_name}'. "
			f"Please run 'bench --site {site_name} migrate' to create it.",
			"OAuth Auto-Config Error"
		)
		frappe.throw(_(
			"Mobile OAuth Settings DocType is not available on site '{site_name}'. "
			"Please run 'bench --site {site_name} migrate' to create it."
		).format(site_name=site_name))
	
	# Try to load the Mobile OAuth Settings single document
	try:
		settings = frappe.get_single("Mobile OAuth Settings")
	except Exception:
		# Document doesn't exist, create it
		settings = frappe.get_doc({
			"doctype": "Mobile OAuth Settings",
			"name": "Mobile OAuth Settings"
		})
		settings.insert(ignore_permissions=True)
		frappe.db.commit()
	
	# If client_id is already set, return settings
	if settings.client_id:
		return settings
	
	# client_id is empty, need to create OAuth Client
	# Check if OAuth Provider is available
	if not frappe.db.exists("DocType", "OAuth Client"):
		frappe.log_error(
			"OAuth Provider not installed. Please install frappe.integrations.oauth2_provider",
			"OAuth Auto-Config Error"
		)
		frappe.throw(_("OAuth Provider is not available on this site. Please contact system administrator."))
	
	# Get current site name
	site_name = frappe.local.site if frappe.local else "Unknown"
	
	# Create new OAuth Client
	client_doc = frappe.new_doc("OAuth Client")
	client_doc.app_name = "Mobile App"
	client_doc.client_name = f"Mobile App - {site_name}"
	
	# Set redirect URIs
	redirect_uri = "app.trust://oauth2redirect"
	client_doc.redirect_uris = redirect_uri
	client_doc.default_redirect_uri = redirect_uri
	
	# Set scopes
	client_doc.scopes = "all openid"
	
	# Set grant type
	# Note: Frappe's OAuth Client uses grant_type as single select field
	# Valid values are: "Authorization Code" or "Implicit"
	# Password and refresh token grants are handled by Frappe OAuth2 provider
	# automatically based on request parameters, not stored in OAuth Client settings
	if hasattr(client_doc, "grant_type"):
		client_doc.grant_type = "Authorization Code"  # This enables PKCE
	
	# Set response type for Authorization Code flow
	if hasattr(client_doc, "response_type"):
		client_doc.response_type = "Code"
	
	# Enable skip authorization for trusted first-party apps
	if hasattr(client_doc, "skip_authorization"):
		client_doc.skip_authorization = 1
	
	# Insert the OAuth Client (client_id and client_secret are auto-generated)
	client_doc.insert(ignore_permissions=True)
	frappe.db.commit()
	
	# Update Mobile OAuth Settings with the OAuth Client info
	settings.client_id = client_doc.client_id
	settings.scope = client_doc.scopes or "all openid"
	settings.redirect_uri = client_doc.default_redirect_uri or redirect_uri
	settings.save(ignore_permissions=True)
	frappe.db.commit()
	
	return settings


@frappe.whitelist(allow_guest=True)
def get_oauth_config():
	"""
	Get OAuth 2.0 configuration for the current site.
	This endpoint is called by mobile clients to retrieve the site-specific
	OAuth configuration (client_id, scope, redirect_uri) instead of hardcoding
	these values in the app.
	
	Security: Only returns client_id if the request Host belongs to the site's configured domains.
	Automatically creates OAuth Client and Mobile OAuth Settings if they don't exist.
	
	Returns:
		{
			"message": {
				"client_id": str,
				"scope": str,
				"redirect_uri": str
			}
		}
	
	Raises:
		frappe.exceptions.ValidationError: If host is not in site's allowed domains or OAuth setup fails
	"""
	# Step 1: Validate Host header (deny by default if not in allowed domains)
	# This MUST be the first check - no client_id should be returned if host is invalid
	_validate_host()
	
	# Step 2: Ensure OAuth settings exist and are configured
	# This will create OAuth Client automatically if needed (idempotent)
	try:
		settings = _ensure_mobile_oauth_settings()
	except Exception as e:
		# Log the error for debugging
		frappe.log_error(
			f"Failed to ensure OAuth settings: {str(e)}",
			"OAuth Config Error"
		)
		# Re-raise with user-friendly message
		if "OAuth Provider" in str(e):
			frappe.throw(_("OAuth Provider is not available on this site. Please contact system administrator."))
		else:
			frappe.throw(_("Failed to retrieve OAuth configuration. Please contact system administrator."))
	
	# Step 3: Return configuration ONLY if all validations passed
	# No fallback values, no default client_id - only return what's actually configured
	if not settings.client_id:
		frappe.log_error(
			"OAuth settings exist but client_id is empty after ensure_mobile_oauth_settings",
			"OAuth Config Error"
		)
		frappe.throw(_("OAuth configuration is incomplete. Please contact system administrator."))
	
	return {
		"client_id": settings.client_id,
		"scope": settings.scope or "all openid",
		"redirect_uri": settings.redirect_uri or "app.trust://oauth2redirect"
	}


@frappe.whitelist(allow_guest=True)
def test_host_validation(test_host=None, expected_result=None):
	"""
	Test function to verify Host validation.
	For testing purposes only - should be removed in production.
	
	Args:
		test_host: Host to test (default: "facebook.com")
		expected_result: "allow" or "reject" (default: "reject")
	"""
	# Mock request with test host
	class MockRequest:
		def __init__(self, host):
			self.headers = {"Host": host}
	
	original_request = getattr(frappe.local, 'request', None)
	test_host = test_host or "facebook.com"
	expected_result = expected_result or "reject"
	
	try:
		frappe.local.request = MockRequest(test_host)
		_validate_host()
		# Validation passed (host was allowed)
		if expected_result == "allow":
			return {
				"status": "PASSED",
				"message": f"Host '{test_host}' was ALLOWED as expected"
			}
		else:
			return {
				"status": "FAILED",
				"message": f"Host '{test_host}' was ALLOWED but should be REJECTED!"
			}
	except frappe.exceptions.ValidationError as e:
		# Validation failed (host was rejected)
		if expected_result == "reject":
			return {
				"status": "PASSED",
				"message": f"Host '{test_host}' was REJECTED as expected",
				"error": str(e)[:200]
			}
		else:
			return {
				"status": "FAILED",
				"message": f"Host '{test_host}' was REJECTED but should be ALLOWED!",
				"error": str(e)[:200]
			}
	except Exception as e:
		return {
			"status": "ERROR",
			"message": f"Unexpected error: {type(e).__name__}",
			"error": str(e)[:200]
		}
	finally:
		if original_request:
			frappe.local.request = original_request


@frappe.whitelist()
def create_task(title=None, status=None, priority=None, start_date=None, 
				task_type=None, description=None, assigned_to=None, due_date=None,
				reference_doctype=None, reference_docname=None,
				assigned_to_list=None, meeting_attendees=None,
				**kwargs):
	"""
	Create a new CRM Task with full field support.
	
	Args:
		title: Task title
		status: Task status (default: "Todo")
		priority: Task priority (default: "Medium")
		start_date: Task start date (default: today)
		task_type: Task type - required (Meeting/Property Showing/Call)
		description: Task description
		assigned_to: Single user email to assign (legacy support)
		assigned_to_list: List of user emails to assign (new way)
		due_date: Task due date
		reference_doctype: Reference document type (e.g., "CRM Lead")
		reference_docname: Reference document name
		meeting_attendees: List of user objects with email, name, profile_pic, id
		**kwargs: Any other fields from CRM Task doctype
	
	Returns:
		Full task JSON with all fields
	"""
	# Validate required fields
	if not task_type:
		frappe.throw(_("Task Type is required"))
	
	# Set defaults
	if not status:
		status = "Todo"
	if not priority:
		priority = "Medium"
	if not start_date:
		start_date = today()
	
	# Get CRM Task meta to validate fields
	task_meta = frappe.get_meta("CRM Task")
	valid_fields = {f.fieldname for f in task_meta.fields}
	
	# Create task with all available fields
	task_doc = {
		"doctype": "CRM Task",
		"task_type": task_type,
		"status": status,
		"priority": priority,
		"start_date": start_date,
	}
	
	# Add standard fields if provided
	if title is not None:
		task_doc["title"] = title
	if description is not None:
		task_doc["description"] = description
	if due_date is not None:
		task_doc["due_date"] = due_date
	if reference_doctype is not None:
		task_doc["reference_doctype"] = reference_doctype
	if reference_docname is not None:
		task_doc["reference_docname"] = reference_docname
	
	# Handle assigned_to (single user - legacy)
	if assigned_to is not None:
		task_doc["assigned_to"] = assigned_to
	
	# Handle link fields that need validation/resolution
	# Project Unit field - resolve name to ID if needed
	project_unit = kwargs.get("project_unit")
	if project_unit:
		if frappe.db.exists("Project Unit", project_unit):
			task_doc["project_unit"] = project_unit
		else:
			# Try to find by unit_name
			unit_doc = frappe.get_all("Project Unit", filters={"unit_name": project_unit}, fields=["name"], limit=1)
			if unit_doc:
				task_doc["project_unit"] = unit_doc[0].name
			else:
				# If not found, don't set it (or throw error if you want strict validation)
				# For now, we'll skip it to avoid errors
				pass
	
	# Unit field - resolve name to ID if needed
	unit = kwargs.get("unit")
	if unit:
		if frappe.db.exists("Unit", unit):
			task_doc["unit"] = unit
		else:
			# Try to find by unit_name
			unit_doc = frappe.get_all("Unit", filters={"unit_name": unit}, fields=["name"], limit=1)
			if unit_doc:
				task_doc["unit"] = unit_doc[0].name
			else:
				# If not found, don't set it
				pass
	
	# Add any other valid fields from kwargs (excluding already handled fields)
	excluded_fields = {"project_unit", "unit"}  # Fields we've already handled
	
	# Get field metadata for link field validation
	link_fields = {}
	for field in task_meta.fields:
		if field.fieldtype == "Link" and field.options:
			link_fields[field.fieldname] = field.options
	
	# Process remaining fields from kwargs
	for key, value in kwargs.items():
		if key in valid_fields and value is not None and key not in excluded_fields:
			# If this is a link field, validate it exists
			if key in link_fields:
				link_doctype = link_fields[key]
				# Check if value exists as ID
				if frappe.db.exists(link_doctype, value):
					task_doc[key] = value
				else:
					# Try to find by name field (common pattern)
					# Most doctypes have a 'name' field that can be searched
					try:
						# Try common name fields
						name_fields = ["name", "title", "full_name", "lead_name", "unit_name", "project_name"]
						found = False
						for name_field in name_fields:
							if frappe.db.exists(link_doctype, {name_field: value}):
								task_doc[key] = frappe.db.get_value(link_doctype, {name_field: value}, "name")
								found = True
								break
						
						# If not found, try get_all with filters
						if not found:
							# Get meta to find the main name field
							link_meta = frappe.get_meta(link_doctype)
							# Try to find by the first Data field that might be a name
							for link_field in link_meta.fields:
								if link_field.fieldtype == "Data" and link_field.fieldname not in ["name"]:
									doc = frappe.get_all(link_doctype, filters={link_field.fieldname: value}, fields=["name"], limit=1)
									if doc:
										task_doc[key] = doc[0].name
										found = True
										break
						
						# If still not found, skip it to avoid LinkValidationError
						if not found:
							pass  # Skip invalid link field
					except Exception:
						# If any error occurs, skip this field
						pass
			else:
				# Not a link field, add directly
				task_doc[key] = value
	
	# Create task document
	task = frappe.get_doc(task_doc)
	
	# Handle meeting_attendees (Table MultiSelect)
	if meeting_attendees is not None:
		if isinstance(meeting_attendees, str):
			try:
				meeting_attendees = frappe.parse_json(meeting_attendees)
			except:
				meeting_attendees = []
		
		if isinstance(meeting_attendees, list):
			task.meeting_attendees = []
			for attendee in meeting_attendees:
				if isinstance(attendee, dict):
					# Extract email from attendee object
					attendee_email = attendee.get("email") or attendee.get("id")
					if attendee_email:
						# Ensure user exists from mobile data
						attendee_email = _ensure_user_from_mobile_data(
							email=attendee_email,
							name=attendee.get("name"),
							profile_pic=attendee.get("profile_pic"),
							user_id=attendee.get("id")
						)
						if attendee_email:
							task.append("meeting_attendees", {
								"crm_task_user": attendee_email
							})
				elif isinstance(attendee, str):
					# Direct email string
					if attendee:
						task.append("meeting_attendees", {
							"crm_task_user": attendee
						})
	
	task.insert()
	frappe.db.commit()
	
	# Handle assigned_to_list (multiple users via Frappe's assign_to system)
	users_to_assign = []
	if assigned_to_list is not None:
		if isinstance(assigned_to_list, str):
			try:
				assigned_to_list = frappe.parse_json(assigned_to_list)
			except:
				assigned_to_list = [assigned_to_list]
		
		if isinstance(assigned_to_list, list):
			for user_data in assigned_to_list:
				if isinstance(user_data, dict):
					# Extract email from user object
					user_email = user_data.get("email") or user_data.get("id")
					if user_email:
						# Ensure user exists from mobile data
						user_email = _ensure_user_from_mobile_data(
							email=user_email,
							name=user_data.get("name"),
							profile_pic=user_data.get("profile_pic"),
							user_id=user_data.get("id")
						)
						if user_email:
							users_to_assign.append(user_email)
				elif isinstance(user_data, str):
					# Direct email string
					if user_data:
						users_to_assign.append(user_data)
	
	# Also add single assigned_to if provided
	if assigned_to and assigned_to not in users_to_assign:
		users_to_assign.append(assigned_to)
	
	# Assign task to all users
	for user_email in users_to_assign:
		try:
			assign_task({
				"doctype": "CRM Task",
				"name": task.name,
				"assign_to": [user_email],
				"description": task.title or task.description or "",
			})
		except Exception as e:
			frappe.log_error(f"Failed to assign task {task.name} to {user_email}: {str(e)}", "Task Assignment Error")
	
	frappe.db.commit()
	
	# Return full task with all fields
	return get_compact_task(task, return_all_fields=True)


@frappe.whitelist()
def edit_task(task_id=None, name=None, title=None, status=None, priority=None, start_date=None,
			  task_type=None, description=None, assigned_to=None, due_date=None,
			  reference_doctype=None, reference_docname=None,
			  assigned_to_list=None, meeting_attendees=None,
			  **kwargs):
	"""
	Edit an existing CRM Task with full field support.
	
	Args:
		task_id: Task ID (name) - required (can also use 'name')
		name: Task name (alias for task_id)
		title: Task title
		status: Task status
		priority: Task priority
		start_date: Task start date
		task_type: Task type
		description: Task description
		assigned_to: Single user email to assign (legacy support)
		assigned_to_list: List of user emails to assign (new way)
		due_date: Task due date
		reference_doctype: Reference document type (e.g., "CRM Lead")
		reference_docname: Reference document name
		meeting_attendees: List of user objects with email, name, profile_pic, id
		**kwargs: Any other fields from CRM Task doctype
	
	Returns:
		Updated full task JSON with all fields
	"""
	# Accept either task_id or name
	task_name = task_id or name
	if not task_name:
		frappe.throw(_("Task ID is required"))
	
	name = task_name
	
	# Get task (this respects permissions)
	task = frappe.get_doc("CRM Task", name)
	
	# Get CRM Task meta to validate fields
	task_meta = frappe.get_meta("CRM Task")
	valid_fields = {f.fieldname for f in task_meta.fields}
	
	# Update standard fields if provided
	if title is not None:
		task.title = title
	if status is not None:
		task.status = status
	if priority is not None:
		task.priority = priority
	if start_date is not None:
		task.start_date = start_date
	if task_type is not None:
		task.task_type = task_type
	if description is not None and hasattr(task, "description"):
		task.description = description
	if due_date is not None and hasattr(task, "due_date"):
		task.due_date = due_date
	if reference_doctype is not None and hasattr(task, "reference_doctype"):
		task.reference_doctype = reference_doctype
	if reference_docname is not None and hasattr(task, "reference_docname"):
		task.reference_docname = reference_docname
	
	# Get field metadata for link field validation
	link_fields = {}
	for field in task_meta.fields:
		if field.fieldtype == "Link" and field.options:
			link_fields[field.fieldname] = field.options
	
	# Update any other valid fields from kwargs
	for key, value in kwargs.items():
		if key in valid_fields and hasattr(task, key) and value is not None:
			# If this is a link field, validate it exists
			if key in link_fields:
				link_doctype = link_fields[key]
				# Check if value exists as ID
				if frappe.db.exists(link_doctype, value):
					setattr(task, key, value)
				else:
					# Try to find by name field (common pattern)
					try:
						# Try common name fields
						name_fields = ["name", "title", "full_name", "lead_name", "unit_name", "project_name"]
						found = False
						for name_field in name_fields:
							if frappe.db.exists(link_doctype, {name_field: value}):
								link_id = frappe.db.get_value(link_doctype, {name_field: value}, "name")
								setattr(task, key, link_id)
								found = True
								break
						
						# If not found, try get_all with filters
						if not found:
							# Get meta to find the main name field
							link_meta = frappe.get_meta(link_doctype)
							# Try to find by the first Data field that might be a name
							for link_field in link_meta.fields:
								if link_field.fieldtype == "Data" and link_field.fieldname not in ["name"]:
									doc = frappe.get_all(link_doctype, filters={link_field.fieldname: value}, fields=["name"], limit=1)
									if doc:
										setattr(task, key, doc[0].name)
										found = True
										break
						
						# If still not found, skip it to avoid LinkValidationError
						if not found:
							pass  # Skip invalid link field
					except Exception:
						# If any error occurs, skip this field
						pass
			else:
				# Not a link field, set directly
				setattr(task, key, value)
	
	# Handle meeting_attendees (Table MultiSelect)
	if meeting_attendees is not None:
		if isinstance(meeting_attendees, str):
			try:
				meeting_attendees = frappe.parse_json(meeting_attendees)
			except:
				meeting_attendees = []
		
		if isinstance(meeting_attendees, list):
			task.meeting_attendees = []
			for attendee in meeting_attendees:
				if isinstance(attendee, dict):
					# Extract email from attendee object
					attendee_email = attendee.get("email") or attendee.get("id")
					if attendee_email:
						# Ensure user exists from mobile data
						attendee_email = _ensure_user_from_mobile_data(
							email=attendee_email,
							name=attendee.get("name"),
							profile_pic=attendee.get("profile_pic"),
							user_id=attendee.get("id")
						)
						if attendee_email:
							task.append("meeting_attendees", {
								"crm_task_user": attendee_email
							})
				elif isinstance(attendee, str):
					# Direct email string
					if attendee:
						task.append("meeting_attendees", {
							"crm_task_user": attendee
						})
	
	task.save()
	frappe.db.commit()
	
	# Handle assigned_to_list (multiple users via Frappe's assign_to system)
	users_to_assign = []
	if assigned_to_list is not None:
		if isinstance(assigned_to_list, str):
			try:
				assigned_to_list = frappe.parse_json(assigned_to_list)
			except:
				assigned_to_list = [assigned_to_list]
		
		if isinstance(assigned_to_list, list):
			for user_data in assigned_to_list:
				if isinstance(user_data, dict):
					# Extract email from user object
					user_email = user_data.get("email") or user_data.get("id")
					if user_email:
						# Ensure user exists from mobile data
						user_email = _ensure_user_from_mobile_data(
							email=user_email,
							name=user_data.get("name"),
							profile_pic=user_data.get("profile_pic"),
							user_id=user_data.get("id")
						)
						if user_email:
							users_to_assign.append(user_email)
				elif isinstance(user_data, str):
					# Direct email string
					if user_data:
						users_to_assign.append(user_data)
	
	# Also add single assigned_to if provided
	if assigned_to is not None:
		if assigned_to not in users_to_assign:
			users_to_assign.append(assigned_to)
	
	# Update assignments: remove old ones and add new ones
	if assigned_to_list is not None or assigned_to is not None:
		# Get current assigned users
		current_todos = frappe.get_all(
			"ToDo",
			filters={
				"reference_type": "CRM Task",
				"reference_name": task.name,
				"status": "Open"
			},
			fields=["allocated_to"],
			distinct=True
		)
		current_users = {todo.allocated_to for todo in current_todos if todo.allocated_to}
		
		# Remove users not in new list
		users_to_remove = current_users - set(users_to_assign)
		for user_email in users_to_remove:
			try:
				unassign_task("CRM Task", task.name, user_email)
			except Exception as e:
				frappe.log_error(f"Failed to unassign task {task.name} from {user_email}: {str(e)}", "Task Unassignment Error")
		
		# Add new users
		users_to_add = set(users_to_assign) - current_users
		for user_email in users_to_add:
			try:
				assign_task({
					"doctype": "CRM Task",
					"name": task.name,
					"assign_to": [user_email],
					"description": task.title or task.description or "",
				})
			except Exception as e:
				frappe.log_error(f"Failed to assign task {task.name} to {user_email}: {str(e)}", "Task Assignment Error")
	
	frappe.db.commit()
	
	# Return full task with all fields
	return get_compact_task(task, return_all_fields=True)


@frappe.whitelist()
def update_task(task_id=None, name=None, title=None, status=None, priority=None, start_date=None,
			  task_type=None, description=None, assigned_to=None, due_date=None,
			  reference_doctype=None, reference_docname=None,
			  assigned_to_list=None, meeting_attendees=None,
			  **kwargs):
	"""
	Update an existing CRM Task (alias for edit_task).
	
	This is an alias for edit_task to maintain API consistency.
	See edit_task for full documentation.
	"""
	return edit_task(
		task_id=task_id, name=name, title=title, status=status, priority=priority,
		start_date=start_date, task_type=task_type, description=description,
		assigned_to=assigned_to, due_date=due_date,
		reference_doctype=reference_doctype, reference_docname=reference_docname,
		assigned_to_list=assigned_to_list, meeting_attendees=meeting_attendees,
		**kwargs
	)


@frappe.whitelist()
def delete_task(task_id=None, name=None):
	"""
	Delete a CRM Task.
	
	Args:
		task_id: Task ID (name) - required (can also use 'name')
		name: Task name (alias for task_id)
	
	Returns:
		{"ok": true, "message": "Task deleted successfully"}
	"""
	# Accept either task_id or name
	task_name = task_id or name
	if not task_name:
		frappe.throw(_("Task ID is required"))
	
	name = task_name
	
	# Delete task (this respects permissions)
	frappe.delete_doc("CRM Task", name)
	frappe.db.commit()
	
	return {"ok": True, "message": f"Task {name} deleted successfully"}


@frappe.whitelist()
def update_status(task_id=None, name=None, status=None):
	"""
	Update task status.
	
	Args:
		task_id: Task ID (name) - required (can also use 'name')
		name: Task name (alias for task_id)
		status: New status (required)
	
	Returns:
		Updated compact task JSON
	"""
	# Accept either task_id or name
	task_name = task_id or name
	if not task_name:
		frappe.throw(_("Task ID is required"))
	if not status:
		frappe.throw(_("Status is required"))
	
	name = task_name
	
	task = frappe.get_doc("CRM Task", name)
	task.status = status
	task.save()
	frappe.db.commit()
	
	return get_compact_task(task)


@frappe.whitelist()
def filter_tasks(date_from=None, date_to=None, importance=None, status=None,
				 limit=20, page=1, order_by="modified desc"):
	"""
	Filter and search CRM Tasks with page-based pagination.
	
	Args:
		date_from: Start date filter (YYYY-MM-DD)
		date_to: End date filter (YYYY-MM-DD)
		importance: Comma-separated priority values (e.g., "High,Medium")
		status: Comma-separated status values (e.g., "Todo,In Progress")
		limit: Page size - maximum results per page (default: 20)
		page: Page number (1-based, default: 1)
		order_by: Sort order (default: "modified desc")
	
	Returns:
		{
			"message": {
				"data": [tasks...],
				"page": current_page,
				"page_size": limit,
				"total": total_matching_tasks,
				"has_next": boolean
			}
		}
	"""
	# Convert and validate pagination params safely
	limit = cint(limit) or 20
	page = cint(page) or 1
	if page < 1:
		page = 1
	
	# Compute offset from page number
	start = (page - 1) * limit
	
	# Build filters as a list of conditions
	filters = []
	if date_from:
		filters.append(["start_date", ">=", date_from])
	if date_to:
		filters.append(["start_date", "<=", date_to])
	
	if importance:
		priorities = [p.strip() for p in importance.split(",") if p.strip()]
		if priorities:
			filters.append(["priority", "in", priorities])
	
	if status:
		statuses = [s.strip() for s in status.split(",") if s.strip()]
		if statuses:
			filters.append(["status", "in", statuses])
	
	# Get safe fields for CRM Task
	base_fields = ["name", "title", "status", "priority", "start_date", "due_date", 
	               "assigned_to", "modified", "description"]
	fields = _safe_fields("CRM Task", base_fields)
	
	# Get tasks with pagination
	tasks = frappe.get_all(
		"CRM Task",
		filters=filters,
		fields=fields,
		order_by=order_by,
		limit_start=start,
		limit_page_length=limit
	)
	
	# Get total count of matching tasks
	total = frappe.db.count("CRM Task", filters=filters)
	
	# Format tasks using compact helper
	data = [get_compact_task(task) for task in tasks]
	
	# Calculate if there are more pages
	has_next = (start + len(data)) < total
	
	return {
		"message": {
			"data": data,
			"page": page,
			"page_size": limit,
			"total": total,
			"has_next": has_next
		}
	}


@frappe.whitelist()
def get_all_tasks(page=1, limit=20, order_by="modified desc",
				  # Filter parameters for all CRM Task fields
				  task_type=None, title=None, priority=None,
				  start_date_from=None, start_date_to=None,
				  due_date_from=None, due_date_to=None,
				  status=None, assigned_to=None,
				  reference_doctype=None, reference_docname=None,
				  description=None, **kwargs):
	"""
	Get all CRM Tasks with pagination and filtering on all fields.
	Returns all available fields for each task.
	
	Args:
		page: Page number (1-based, default: 1)
		limit: Number of tasks per page (default: 20)
		order_by: Sort order (default: "modified desc")
		
		# Filter parameters (all optional):
		task_type: Task type filter (string or comma-separated: "Meeting,Property Showing,Call")
		title: Title text search (partial match)
		priority: Priority filter (string or comma-separated: "Low,Medium,High")
		start_date_from: Start date filter from (YYYY-MM-DD or DD-MM-YYYY)
		start_date_to: Start date filter to (YYYY-MM-DD or DD-MM-YYYY)
		due_date_from: Due date filter from (YYYY-MM-DD or DD-MM-YYYY)
		due_date_to: Due date filter to (YYYY-MM-DD or DD-MM-YYYY)
		status: Status filter (string or comma-separated: "Todo,In Progress,Done")
		assigned_to: Assigned user email or name
		reference_doctype: Reference document type
		reference_docname: Reference document name
		description: Description text search (partial match)
	
	Returns:
		{
			"message": {
				"data": [tasks...],
				"page": current_page,
				"page_size": limit,
				"total": total_tasks,
				"total_pages": total_pages,
				"has_next": boolean,
				"has_previous": boolean
			}
		}
	"""
	# Get parameters from form_dict for GET requests
	if hasattr(frappe, 'form_dict') and frappe.form_dict:
		# Override with form_dict values (query string takes precedence)
		status = frappe.form_dict.get('status') if 'status' in frappe.form_dict else status
		task_type = frappe.form_dict.get('task_type') if 'task_type' in frappe.form_dict else task_type
		title = frappe.form_dict.get('title') if 'title' in frappe.form_dict else title
		priority = frappe.form_dict.get('priority') if 'priority' in frappe.form_dict else priority
		start_date_from = frappe.form_dict.get('start_date_from') if 'start_date_from' in frappe.form_dict else start_date_from
		start_date_to = frappe.form_dict.get('start_date_to') if 'start_date_to' in frappe.form_dict else start_date_to
		due_date_from = frappe.form_dict.get('due_date_from') if 'due_date_from' in frappe.form_dict else due_date_from
		due_date_to = frappe.form_dict.get('due_date_to') if 'due_date_to' in frappe.form_dict else due_date_to
		assigned_to = frappe.form_dict.get('assigned_to') if 'assigned_to' in frappe.form_dict else assigned_to
		reference_doctype = frappe.form_dict.get('reference_doctype') if 'reference_doctype' in frappe.form_dict else reference_doctype
		reference_docname = frappe.form_dict.get('reference_docname') if 'reference_docname' in frappe.form_dict else reference_docname
		description = frappe.form_dict.get('description') if 'description' in frappe.form_dict else description
		page = frappe.form_dict.get('page') if 'page' in frappe.form_dict else page
		limit = frappe.form_dict.get('limit') if 'limit' in frappe.form_dict else limit
		order_by = frappe.form_dict.get('order_by') if 'order_by' in frappe.form_dict else order_by
	
	page = cint(page) or 1
	limit = cint(limit) or 20
	
	if page < 1:
		page = 1
	if limit < 1:
		limit = 20
	if limit > 100:
		limit = 100  # Cap at 100 for performance
	
	# Calculate offset
	start = (page - 1) * limit
	
	# Build filters dynamically
	filters = []
	
	# Task Type filter (ignore empty strings)
	if task_type and str(task_type).strip():
		if isinstance(task_type, str) and "," in task_type:
			task_types = [t.strip() for t in task_type.split(",") if t.strip()]
			if task_types:
				filters.append(["task_type", "in", task_types])
		else:
			filters.append(["task_type", "=", task_type])
	
	# Title filter (text search)
	if title:
		filters.append(["title", "like", f"%{title}%"])
	
	# Priority filter (ignore empty strings)
	if priority and str(priority).strip():
		if isinstance(priority, str) and "," in priority:
			priorities = [p.strip() for p in priority.split(",") if p.strip()]
			if priorities:
				filters.append(["priority", "in", priorities])
		else:
			filters.append(["priority", "=", priority])
	
	# Helper function to normalize date format (DD-MM-YYYY to YYYY-MM-DD)
	def normalize_date(date_str):
		if not date_str:
			return None
		date_str = str(date_str).strip()
		if "-" in date_str:
			parts = date_str.split("-")
			if len(parts) == 3:
				try:
					part1 = int(parts[0])
					part2 = int(parts[1])
					part3 = int(parts[2])
					
					if part1 > 31:
						return date_str
					elif part1 <= 31 and part2 > 12:
						return f"{part3}-{part2:02d}-{part1:02d}"
					elif part1 > 12 and part2 <= 12:
						return f"{part3}-{part2:02d}-{part1:02d}"
					else:
						return date_str
				except ValueError:
					return date_str
		return date_str
	
	# Start Date filters (normalize date format)
	if start_date_from:
		start_date_from = normalize_date(start_date_from)
		if start_date_from:
			if len(start_date_from) == 10:  # YYYY-MM-DD format
				filters.append(["start_date", ">=", f"{start_date_from} 00:00:00"])
			else:
				filters.append(["start_date", ">=", start_date_from])
	if start_date_to:
		start_date_to = normalize_date(start_date_to)
		if start_date_to:
			if len(start_date_to) == 10:  # YYYY-MM-DD format
				filters.append(["start_date", "<=", f"{start_date_to} 23:59:59"])
			else:
				filters.append(["start_date", "<=", start_date_to])
	
	# Due Date filters (normalize date format)
	if due_date_from:
		due_date_from = normalize_date(due_date_from)
		if due_date_from:
			if len(due_date_from) == 10:  # YYYY-MM-DD format
				filters.append(["due_date", ">=", f"{due_date_from} 00:00:00"])
			else:
				filters.append(["due_date", ">=", due_date_from])
	if due_date_to:
		due_date_to = normalize_date(due_date_to)
		if due_date_to:
			if len(due_date_to) == 10:  # YYYY-MM-DD format
				filters.append(["due_date", "<=", f"{due_date_to} 23:59:59"])
			else:
				filters.append(["due_date", "<=", due_date_to])
	
	# Status filter (ignore empty strings)
	if status and str(status).strip():
		statuses = [s.strip() for s in status.split(",") if s.strip()]
		if statuses:
			filters.append(["status", "in", statuses])
	
	# Assigned To filter
	if assigned_to:
		filters.append(["assigned_to", "=", assigned_to])
	
	# Reference DocType filter
	if reference_doctype:
		filters.append(["reference_doctype", "=", reference_doctype])
	
	# Reference DocName filter
	if reference_docname:
		filters.append(["reference_docname", "=", reference_docname])
	
	# Description filter (text search)
	if description:
		filters.append(["description", "like", f"%{description}%"])
	
	# Get total count with filters
	total = frappe.db.count("CRM Task", filters=filters if filters else None)
	
	# Get safe fields for CRM Task
	base_fields = ["name", "title", "status", "priority", "start_date", "due_date", 
	               "assigned_to", "modified", "description", "task_type", "lead", "project", 
	               "unit", "project_unit", "reference_doctype", "reference_docname", 
	               "creation", "owner", "modified_by"]
	fields = _safe_fields("CRM Task", base_fields)
	
	# Get tasks with pagination
	tasks = frappe.get_all(
		"CRM Task",
		filters=filters if filters else None,
		fields=fields,
		order_by=order_by,
		limit_start=start,
		limit_page_length=limit
	)
	
	# Format tasks using compact helper
	data = [get_compact_task(task, return_all_fields=True) for task in tasks]
	
	# Add reminder_at to each task
	if data:
		try:
			task_names = [task.get("name") for task in data if task.get("name")]
			if task_names:
				# Get all reminders for these tasks
				reminders = frappe.get_all(
					"Reminder",
					filters={
						"reference_doctype": "CRM Task",
						"reference_docname": ["in", task_names]
					},
					fields=["reference_docname", "remind_at"]
				)
				
				# Create reminder dict
				reminder_dict = {r.reference_docname: r.remind_at for r in reminders}
				
				# Add reminder_at to each task
				for task in data:
					task_name = task.get("name")
					task["reminder_at"] = reminder_dict.get(task_name, None)
		except Exception as e:
			frappe.log_error(f"Error fetching reminders: {str(e)}", "get_all_tasks_reminders_error")
			# Set reminder_at to None for all tasks if error occurs
			for task in data:
				task["reminder_at"] = None
	
	# Calculate pagination info
	total_pages = (total + limit - 1) // limit if total > 0 else 0
	has_next = (start + len(data)) < total
	has_previous = page > 1
	
	return {
		"message": {
			"data": data,
			"page": page,
			"page_size": limit,
			"total": total,
			"total_pages": total_pages,
			"has_next": has_next,
			"has_previous": has_previous
		}
	}
@frappe.whitelist()
def home_tasks(limit=5):
	"""
	Get today's top tasks for home screen.
	Returns all available fields for each task.
	
	Args:
		limit: Maximum number of tasks to return (default: 5)
	
	Returns:
		{"today": [tasks...], "limit": N}
	"""
	today_date = today()
	tomorrow_date = add_days(today_date, 1)
	
	# Get task names first (lightweight query)
	# NOTE: Using start_date (not due_date) to filter today's tasks
	# start_date is Datetime field, so we need to use range filter
	task_names = frappe.get_all(
		"CRM Task",
		filters=[
			["start_date", ">=", f"{today_date} 00:00:00"],
			["start_date", "<", f"{tomorrow_date} 00:00:00"]
		],
		fields=["name"],
		order_by="priority desc, modified desc",
		page_length=cint(limit) or 5
	)
	
	# Get full task documents with all fields
	data = []
	for task_name_obj in task_names:
		try:
			task_doc = frappe.get_doc("CRM Task", task_name_obj.name)
			data.append(get_compact_task(task_doc, return_all_fields=True))
		except Exception:
			# Skip tasks that can't be loaded (permissions, deleted, etc.)
			continue
	
	return {
		"today": data,
		"limit": cint(limit) or 5
	}


@frappe.whitelist()
def main_page_buckets(min_each=5):
	"""
	Get tasks organized into today/late/upcoming buckets.
	Each bucket will contain at least min_each tasks (when available).
	Returns all available fields for each task.
	
	Args:
		min_each: Minimum number of tasks per bucket (default: 5)
	
	Returns:
		{
			"today": [tasks...],
			"late": [tasks...],
			"upcoming": [tasks...],
			"min_each": N
		}
	"""
	today_date = today()
	tomorrow_date = add_days(today_date, 1)
	min_count = cint(min_each) or 5
	
	# Active statuses (not Done or Canceled)
	active_statuses = ["Backlog", "Todo", "In Progress"]
	
	def get_tasks_with_all_fields(filters, order_by, page_length):
		"""Helper to get task names first, then load full documents."""
		task_names = frappe.get_all(
			"CRM Task",
			filters=filters,
			fields=["name"],
			order_by=order_by,
			page_length=page_length
		)
		
		tasks = []
		for task_name_obj in task_names:
			try:
				task_doc = frappe.get_doc("CRM Task", task_name_obj.name)
				tasks.append(get_compact_task(task_doc, return_all_fields=True))
			except Exception:
				# Skip tasks that can't be loaded (permissions, deleted, etc.)
				continue
		return tasks
	
	# Today's tasks - using start_date (not due_date)
	# start_date is Datetime field, so we need to use range filter
	today_tasks = get_tasks_with_all_fields(
		filters=[
			["start_date", ">=", f"{today_date} 00:00:00"],
			["start_date", "<", f"{tomorrow_date} 00:00:00"]
		],
		order_by="priority desc, modified desc",
		page_length=min_count
	)
	
	# Late tasks (before today and still active) - using start_date (not due_date)
	late_tasks = get_tasks_with_all_fields(
		filters=[
			["start_date", "<", f"{today_date} 00:00:00"],
			["status", "in", active_statuses]
		],
		order_by="start_date asc, priority desc",
		page_length=min_count
	)
	
	# Upcoming tasks (after today) - using start_date (not due_date)
	upcoming_tasks = get_tasks_with_all_fields(
		filters=[["start_date", ">=", f"{tomorrow_date} 00:00:00"]],
		order_by="start_date asc, priority desc",
		page_length=min_count
	)
	
	return {
		"today": today_tasks,
		"late": late_tasks,
		"upcoming": upcoming_tasks,
		"min_each": min_count
	}


@frappe.whitelist()
def get_crm_leads(limit=100, search_term=None):
	"""
	Get list of CRM Leads for reference selection.
	
	Args:
		limit: Maximum number of leads to return (default: 100)
		search_term: Optional search term to filter leads by name or email
	
	Returns:
		List of leads with name and label for display
	"""
	limit = cint(limit) or 100
	if limit > 500:
		limit = 500  # Cap at 500 for performance
	
	filters = {}
	if search_term:
		search_term = f"%{search_term}%"
		filters = [
			["lead_name", "like", search_term],
			"or",
			["email", "like", search_term],
			"or",
			["mobile_no", "like", search_term]
		]
	
	# Get leads with name and lead_name (title field)
	leads = frappe.get_all(
		"CRM Lead",
		filters=filters if filters else None,
		fields=["name", "lead_name", "email", "mobile_no", "organization"],
		order_by="modified desc",
		limit_page_length=limit
	)
	
	# Format response
	result = []
	for lead in leads:
		# Create display label: lead_name or organization or email or name
		label = lead.get("lead_name") or lead.get("organization") or lead.get("email") or lead.get("name")
		
		result.append({
			"name": lead.name,
			"label": label,
			"email": lead.get("email"),
			"mobile_no": lead.get("mobile_no")
		})
	
	return {"message": result}


@frappe.whitelist()
def get_real_estate_projects(limit=100, search_term=None):
	"""
	Get list of Real Estate Projects for reference selection.
	
	Args:
		limit: Maximum number of projects to return (default: 100)
		search_term: Optional search term to filter projects by name
	
	Returns:
		List of projects with name and label for display
	"""
	limit = cint(limit) or 100
	if limit > 500:
		limit = 500  # Cap at 500 for performance
	
	filters = {}
	if search_term:
		search_term = f"%{search_term}%"
		filters = ["project_name", "like", search_term]
	
	# Get projects with name and project_name (title field)
	projects = frappe.get_all(
		"Real Estate Project",
		filters=filters if filters else None,
		fields=["name", "project_name", "location", "developer"],
		order_by="modified desc",
		limit_page_length=limit
	)
	
	# Format response
	result = []
	for project in projects:
		# Create display label: project_name with location if available
		label = project.get("project_name") or project.get("name")
		if project.get("location"):
			label = f"{label} - {project.get('location')}"
		
		result.append({
			"name": project.name,
			"label": label,
			"project_name": project.get("project_name"),
			"location": project.get("location"),
			"developer": project.get("developer")
		})
	
	return {"message": result}


@frappe.whitelist()
def get_units(limit=100, search_term=None):
	"""
	Get list of Units for reference selection.
	
	Args:
		limit: Maximum number of units to return (default: 100)
		search_term: Optional search term to filter units by name
	
	Returns:
		List of units with name and label for display
	"""
	limit = cint(limit) or 100
	if limit > 500:
		limit = 500  # Cap at 500 for performance
	
	filters = {}
	if search_term:
		search_term = f"%{search_term}%"
		filters = ["unit_name", "like", search_term]
	
	# Get units with name and unit_name (title field)
	units = frappe.get_all(
		"Unit",
		filters=filters if filters else None,
		fields=["name", "unit_name", "type", "city", "price"],
		order_by="modified desc",
		limit_page_length=limit
	)
	
	# Format response
	result = []
	for unit in units:
		# Create display label: unit_name with type and city if available
		label = unit.get("unit_name") or unit.get("name")
		details = []
		if unit.get("type"):
			details.append(unit.get("type"))
		if unit.get("city"):
			details.append(unit.get("city"))
		if details:
			label = f"{label} ({', '.join(details)})"
		
		result.append({
			"name": unit.name,
			"label": label,
			"unit_name": unit.get("unit_name"),
			"type": unit.get("type"),
			"city": unit.get("city"),
			"price": unit.get("price")
		})
	
	return {"message": result}


@frappe.whitelist()
def get_project_units(limit=100, search_term=None, project=None):
	"""
	Get list of Project Units for reference selection.
	
	Args:
		limit: Maximum number of project units to return (default: 100)
		search_term: Optional search term to filter units by name
		project: Optional filter by project name
	
	Returns:
		List of project units with name and label for display
	"""
	limit = cint(limit) or 100
	if limit > 500:
		limit = 500  # Cap at 500 for performance
	
	filters = {}
	if project:
		filters["project"] = project
	
	if search_term:
		search_term = f"%{search_term}%"
		if filters:
			filters = [filters, ["unit_name", "like", search_term]]
		else:
			filters = ["unit_name", "like", search_term]
	
	# Get project units with name, unit_name, and project
	project_units = frappe.get_all(
		"Project Unit",
		filters=filters if filters else None,
		fields=["name", "unit_name", "project", "type", "price"],
		order_by="modified desc",
		limit_page_length=limit
	)
	
	# Format response
	result = []
	for unit in project_units:
		# Create display label: unit_name with project name if available
		label = unit.get("unit_name") or unit.get("name")
		if unit.get("project"):
			label = f"{label} - {unit.get('project')}"
		if unit.get("type"):
			label = f"{label} ({unit.get('type')})"
		
		result.append({
			"name": unit.name,
			"label": label,
			"unit_name": unit.get("unit_name"),
			"project": unit.get("project"),
			"type": unit.get("type"),
			"price": unit.get("price")
		})
	
	return {"message": result}


@frappe.whitelist()
def get_current_user_role():
	"""
	Get the current user's role.
	Returns the primary role based on priority:
	- System Manager (highest priority)
	- Sales Master Manager
	- Sales Manager
	- Sales User
	- Guest (lowest priority)
	
	Returns:
		{
			"role": String,           # Primary role name
			"roles": List[String],    # All user roles
			"user": String,           # User email
			"full_name": String?      # User full name
		}
	"""
	user = frappe.session.user
	
	if not user or user == "Guest":
		return {
			"role": "Guest",
			"roles": ["Guest"],
			"user": "Guest",
			"full_name": "Guest"
		}
	
	# Get all user roles
	roles = frappe.get_roles(user)
	
	# Determine primary role based on priority
	primary_role = ""
	
	if "System Manager" in roles:
		primary_role = "System Manager"
	elif "Sales Master Manager" in roles:
		primary_role = "Sales Master Manager"
	elif "Sales Manager" in roles:
		primary_role = "Sales Manager"
	elif "Sales User" in roles:
		primary_role = "Sales User"
	elif "Guest" in roles:
		primary_role = "Guest"
	else:
		# If no known role found, return first role or "Unknown"
		primary_role = roles[0] if roles else "Unknown"
	
	# Get user full name
	try:
		user_doc = frappe.get_doc("User", user)
		full_name = user_doc.full_name or user_doc.name
	except Exception:
		full_name = user
	
	return {
		"role": primary_role,
		"roles": roles,
		"user": user,
		"full_name": full_name
	}


@frappe.whitelist()
def get_my_team_members():
	"""
	Get team members for the current user if they are a Team Leader.
	
	Returns:
		{
			"team_leader": String,        # Current user email
			"team_name": String?,         # Team name (team_leader value)
			"members": List[UserObject],  # List of team members
			"count": int                  # Number of members
		}
		
		If user is not a Team Leader:
		{
			"team_leader": String,
			"team_name": None,
			"members": [],
			"count": 0,
			"message": "User is not a Team Leader"
		}
	"""
	user = frappe.session.user
	
	if not user or user == "Guest":
		return {
			"team_leader": "Guest",
			"team_name": None,
			"members": [],
			"count": 0,
			"message": "Guest users cannot be Team Leaders"
		}
	
	# Find Team where current user is team_leader
	teams = frappe.get_all(
		"Team",
		filters={"team_leader": user},
		fields=["name", "team_leader"],
		limit=1
	)
	
	if not teams:
		return {
			"team_leader": user,
			"team_name": None,
			"members": [],
			"count": 0,
			"message": "User is not a Team Leader"
		}
	
	team = teams[0]
	team_name = team.name
	
	# Get team members from Member child table
	members = frappe.get_all(
		"Member",
		filters={
			"parent": team_name,
			"parenttype": "Team"
		},
		fields=["member"],
		order_by="member asc"
	)
	
	# Get user details for each member
	member_list = []
	for member_row in members:
		member_email = member_row.get("member")
		if not member_email:
			continue
		
		try:
			user_doc = frappe.get_doc("User", member_email)
			member_data = {
				"email": user_doc.email or member_email,
				"name": user_doc.full_name or user_doc.name,
			}
			
			# Get profile picture if available
			if hasattr(user_doc, "user_image") and user_doc.user_image:
				member_data["profile_pic"] = user_doc.user_image
			elif hasattr(user_doc, "photo") and user_doc.photo:
				member_data["profile_pic"] = user_doc.photo
			else:
				member_data["profile_pic"] = None
			
			member_list.append(member_data)
		except frappe.DoesNotExistError:
			# User doesn't exist, skip
			continue
		except Exception:
			# Error fetching user, skip
			continue
	
	return {
		"team_leader": user,
		"team_name": team_name,
		"members": member_list,
		"count": len(member_list)
	}


def get_compact_lead(lead, return_all_fields=False):
	"""
	Return lead representation.
	Accepts both Document objects and dict-like objects (frappe._dict).
	
	Args:
		lead: Lead document or dict
		return_all_fields: If True, return all available fields from lead object
	"""
	# Handle both dict-like and Document objects
	def _get(obj, key, default=None):
		if isinstance(obj, dict):
			return obj.get(key, default)
		return getattr(obj, key, default)
	
	# Get lead name/id
	lead_name = lead.name if hasattr(lead, "name") else lead.get("name")
	
	# If return_all_fields is True, return all fields from lead object
	if return_all_fields:
		result = {}
		# Get all fields from lead object
		if isinstance(lead, dict):
			# Dict-like object - copy all fields except internal ones
			# Include all fields even if value is None (to ensure all requested fields are returned)
			for key, value in lead.items():
				if key not in ['doctype']:
					result[key] = value
			# Ensure name field is always included
			if 'name' not in result and lead_name:
				result['name'] = lead_name
		else:
			# Document object - get all fields from meta
			for field in lead.meta.fields:
				fieldname = field.fieldname
				# Skip internal/system fields
				if fieldname in ['doctype']:
					continue
				# Skip child tables (they're handled separately if needed)
				if field.fieldtype == 'Table':
					continue
				# Get field value
				value = getattr(lead, fieldname, None)
				# Include field if it has a value or is a standard/important field
				important_fields = ['name', 'modified', 'creation', 'owner', 'modified_by', 'lead_name', 'email', 'mobile_no', 'organization', 'status',
				                    'request', 'feedback', 'last_contacted', 'assigned_date', 'lead_score', 'lead_rating', 'rating_reason',
				                    'salutation', 'gender', 'first_name', 'last_name', 'middle_name', 'job_title', 'website', 'phone',
				                    'source', 'industry', 'territory', 'lead_owner', 'project', 'project_unit', 'single_unit', 'campaign',
				                    'converted', 'delayed', 'no_of_employees', 'annual_revenue', 'best_time_contacte', 'custom_meta_lead_id',
				                    'original_lead', 'naming_series', 'image', 'sla', 'sla_status', 'communication_status', 'response_by',
				                    'first_response_time', 'first_responded_on', 'is_duplicate', 'duplicated_from']
				# Include all fields (even if None) when return_all_fields is True
				result[fieldname] = value
			# Ensure standard fields are included
			result['name'] = lead.name
			if hasattr(lead, 'modified'):
				result['modified'] = lead.modified
			if hasattr(lead, 'creation'):
				result['creation'] = lead.creation
			if hasattr(lead, 'owner'):
				result['owner'] = lead.owner
			if hasattr(lead, 'modified_by'):
				result['modified_by'] = lead.modified_by
	else:
		# Compact mode - return only core fields
		result = {
			"name": lead_name,
			"lead_name": _get(lead, "lead_name") or _get(lead, "organization") or _get(lead, "email") or lead_name,
			"email": _get(lead, "email"),
			"mobile_no": _get(lead, "mobile_no"),
			"status": _get(lead, "status"),
			"modified": _get(lead, "modified")
		}
		
		# Add optional fields if they exist
		organization = _get(lead, "organization")
		if organization is not None:
			result["organization"] = organization
	
	# Expand link fields to return names instead of IDs
	# Status field - return status name
	status_id = _get(result, "status")
	if status_id:
		try:
			status_doc = frappe.get_doc("CRM Lead Status", status_id)
			result["status"] = status_doc.get("lead_status") or status_id
			result["status_id"] = status_id
		except Exception:
			result["status_id"] = status_id
	
	# Source field - return source name
	source_id = _get(result, "source")
	if source_id:
		try:
			source_doc = frappe.get_doc("CRM Lead Source", source_id)
			result["source"] = source_doc.get("source_name") or source_id
			result["source_id"] = source_id
		except Exception:
			result["source_id"] = source_id
	
	# Industry field - return industry name
	industry_id = _get(result, "industry")
	if industry_id:
		try:
			industry_doc = frappe.get_doc("CRM Industry", industry_id)
			result["industry"] = industry_doc.get("industry_name") or industry_id
			result["industry_id"] = industry_id
		except Exception:
			result["industry_id"] = industry_id
	
	# Lead Owner field - return user full name
	lead_owner_id = _get(result, "lead_owner")
	if lead_owner_id:
		try:
			user_doc = frappe.get_doc("User", lead_owner_id)
			result["lead_owner"] = user_doc.get("full_name") or user_doc.get("name") or lead_owner_id
			result["lead_owner_id"] = lead_owner_id
		except Exception:
			result["lead_owner_id"] = lead_owner_id
	
	# Project field - return project_name instead of ID
	project_id = _get(result, "project")
	if project_id:
		try:
			project_doc = frappe.get_doc("Real Estate Project", project_id)
			project_name = project_doc.get("project_name") or project_id
			result["project"] = project_name
			result["project_id"] = project_id
		except Exception:
			result["project_id"] = project_id
	
	# Project Unit field - return unit_name instead of ID
	project_unit_id = _get(result, "project_unit")
	if project_unit_id:
		try:
			project_unit_doc = frappe.get_doc("Project Unit", project_unit_id)
			project_unit_name = project_unit_doc.get("unit_name") or project_unit_doc.get("name") or project_unit_id
			result["project_unit"] = project_unit_name
			result["project_unit_id"] = project_unit_id
		except Exception:
			result["project_unit_id"] = project_unit_id
	
	# Single Unit field - return unit_name instead of ID
	single_unit_id = _get(result, "single_unit")
	if single_unit_id:
		try:
			unit_doc = frappe.get_doc("Unit", single_unit_id)
			unit_name = unit_doc.get("unit_name") or unit_doc.get("name") or single_unit_id
			result["single_unit"] = unit_name
			result["single_unit_id"] = single_unit_id
		except Exception:
			result["single_unit_id"] = single_unit_id
	
	# Get assigned users from ToDo records only (ignore assigned_to field)
	# This matches what's shown in the left sidebar in Frappe UI
	try:
		if lead_name:  # Only get assigned users if lead_name is not None
			assigned_users = _get_assigned_users("CRM Lead", lead_name)
			result["assigned_to"] = assigned_users if assigned_users else []
		else:
			result["assigned_to"] = []
	except Exception:
		# Error getting assigned users, return empty array
		result["assigned_to"] = []
	
	return result


@frappe.whitelist()
def create_lead(lead_name=None, first_name=None, last_name=None, middle_name=None,
			   email=None, mobile_no=None, phone=None, organization=None,
			   status=None, source=None, industry=None, lead_owner=None,
			   project=None, project_unit=None, single_unit=None,
			   job_title=None, website=None, territory=None,
			   assigned_to=None, assigned_to_list=None,
			   comment=None, comment_content=None,
			   **kwargs):
	"""
	Create a new CRM Lead.
	
	Args:
		lead_name: Full name of the lead (auto-generated if not provided)
		first_name: First name (required if lead_name not provided)
		last_name: Last name
		middle_name: Middle name
		email: Email address
		mobile_no: Mobile number (required)
		phone: Other phone number
		organization: Organization name
		status: Lead status (ID or name) - defaults to "New"
		source: Lead source (ID or name)
		industry: Industry (ID or name)
		lead_owner: Lead owner user email (ID or name)
		project: Real Estate Project (ID or name)
		project_unit: Project Unit (ID or name)
		single_unit: Unit (ID or name)
		job_title: Job title
		website: Website URL
		territory: Territory
		comment: Comment content to add after creating the lead (alias for comment_content)
		comment_content: Comment content to add after creating the lead
		**kwargs: Any other fields from CRM Lead doctype
	
	Returns:
		Created lead JSON with all fields
	"""
	# Validate required fields
	if not mobile_no and not email and not organization:
		frappe.throw(_("Mobile number, email, or organization is required"))
	
	# Create new lead document
	lead_doc = frappe.get_doc({
		"doctype": "CRM Lead"
	})
	
	# Set basic fields
	if first_name:
		lead_doc.first_name = first_name
	if last_name:
		lead_doc.last_name = last_name
	if middle_name:
		lead_doc.middle_name = middle_name
	if lead_name:
		lead_doc.lead_name = lead_name
	if email:
		lead_doc.email = email
	if mobile_no:
		lead_doc.mobile_no = mobile_no
	if phone:
		lead_doc.phone = phone
	if organization:
		lead_doc.organization = organization
	if job_title:
		lead_doc.job_title = job_title
	if website:
		lead_doc.website = website
	if territory:
		lead_doc.territory = territory
	
	# Set status (default to "New" if not provided)
	if status:
		# Resolve status (ID or name)
		if frappe.db.exists("CRM Lead Status", status):
			lead_doc.status = status
		else:
			# Try to find by lead_status field
			status_doc = frappe.get_all("CRM Lead Status", filters={"lead_status": status}, fields=["name"], limit=1)
			if status_doc:
				lead_doc.status = status_doc[0].name
			else:
				lead_doc.status = "New"
	else:
		lead_doc.status = "New"
	
	# Handle link fields (with name resolution)
	if source:
		if frappe.db.exists("CRM Lead Source", source):
			lead_doc.source = source
		else:
			source_doc = frappe.get_all("CRM Lead Source", filters={"source_name": source}, fields=["name"], limit=1)
			if source_doc:
				lead_doc.source = source_doc[0].name
			else:
				frappe.throw(_("Cannot find Source: {0}").format(source))
	
	if industry:
		if frappe.db.exists("CRM Industry", industry):
			lead_doc.industry = industry
		else:
			industry_doc = frappe.get_all("CRM Industry", filters={"industry_name": industry}, fields=["name"], limit=1)
			if industry_doc:
				lead_doc.industry = industry_doc[0].name
			else:
				frappe.throw(_("Cannot find Industry: {0}").format(industry))
	
	if lead_owner:
		# Lead owner is a User - check if it's email or name
		if frappe.db.exists("User", lead_owner):
			lead_doc.lead_owner = lead_owner
		else:
			# Try to find by email
			user = frappe.get_all("User", filters={"email": lead_owner}, fields=["name"], limit=1)
			if user:
				lead_doc.lead_owner = user[0].name
			else:
				frappe.throw(_("Cannot find User: {0}").format(lead_owner))
	
	if project:
		if frappe.db.exists("Real Estate Project", project):
			lead_doc.project = project
		else:
			project_doc = frappe.get_all("Real Estate Project", filters={"project_name": project}, fields=["name"], limit=1)
			if project_doc:
				lead_doc.project = project_doc[0].name
			else:
				frappe.throw(_("Cannot find Project: {0}").format(project))
	
	if project_unit:
		if frappe.db.exists("Project Unit", project_unit):
			lead_doc.project_unit = project_unit
		else:
			unit_doc = frappe.get_all("Project Unit", filters={"unit_name": project_unit}, fields=["name"], limit=1)
			if unit_doc:
				lead_doc.project_unit = unit_doc[0].name
			else:
				frappe.throw(_("Cannot find Project Unit: {0}").format(project_unit))
	
	if single_unit:
		if frappe.db.exists("Unit", single_unit):
			lead_doc.single_unit = single_unit
		else:
			unit_doc = frappe.get_all("Unit", filters={"unit_name": single_unit}, fields=["name"], limit=1)
			if unit_doc:
				lead_doc.single_unit = unit_doc[0].name
			else:
				frappe.throw(_("Cannot find Unit: {0}").format(single_unit))
	
	# Update any other valid fields from kwargs
	lead_meta = frappe.get_meta("CRM Lead")
	valid_fields = {f.fieldname for f in lead_meta.fields}
	for key, value in kwargs.items():
		if key in valid_fields and hasattr(lead_doc, key) and value is not None:
			setattr(lead_doc, key, value)
	
	# Insert lead
	lead_doc.insert()
	frappe.db.commit()
	
	# Handle comment (if provided)
	comment_text = comment or comment_content
	if comment_text and str(comment_text).strip():
		try:
			from frappe.desk.form.utils import add_comment
			# Get current user info for comment
			user = frappe.session.user
			user_doc = frappe.get_doc("User", user)
			comment_email = user_doc.email or user
			comment_by = user_doc.full_name or user_doc.name or user
			
			add_comment(
				reference_doctype="CRM Lead",
				reference_name=lead_doc.name,
				content=str(comment_text).strip(),
				comment_email=comment_email,
				comment_by=comment_by
			)
			frappe.db.commit()
		except Exception as e:
			# Log error but don't fail the lead creation
			frappe.log_error(f"Error adding comment to lead {lead_doc.name}: {str(e)}", "create_lead_comment_error")
	
	# Handle assigned_to_list (multiple users via Frappe's assign_to system)
	# Check if assigned_to is a list (mobile app might send list instead of assigned_to_list)
	assigned_to_is_list = False
	if assigned_to is not None:
		if isinstance(assigned_to, list):
			# If assigned_to is a list, treat it as assigned_to_list
			assigned_to_is_list = True
			if assigned_to_list is None:
				assigned_to_list = assigned_to
	
	# Handle assigned_to_list (multiple users via Frappe's assign_to system)
	users_to_assign = []
	
	# Process assigned_to_list first
	if assigned_to_list is not None:
		if isinstance(assigned_to_list, str):
			try:
				assigned_to_list = frappe.parse_json(assigned_to_list)
			except:
				assigned_to_list = [assigned_to_list]
		
		if isinstance(assigned_to_list, list):
			for user_data in assigned_to_list:
				if isinstance(user_data, dict):
					# Extract email from user object
					user_email = user_data.get("email") or user_data.get("id")
					if user_email:
						# Ensure user exists from mobile data
						user_email = _ensure_user_from_mobile_data(
							email=user_email,
							name=user_data.get("name"),
							profile_pic=user_data.get("profile_pic"),
							user_id=user_data.get("id")
						)
						if user_email and user_email not in users_to_assign:
							users_to_assign.append(user_email)
				elif isinstance(user_data, str):
					# Direct email string
					if user_data and user_data not in users_to_assign:
						users_to_assign.append(user_data)
	
	# Also add single assigned_to if provided (only if it's a string, not a list)
	# If assigned_to was a list, it was already converted to assigned_to_list above
	if assigned_to and not assigned_to_is_list:
		if isinstance(assigned_to, str):
			if assigned_to not in users_to_assign:
				users_to_assign.append(assigned_to)
		elif isinstance(assigned_to, list):
			# Handle list of dicts (like mobile app sends)
			for user_data in assigned_to:
				if isinstance(user_data, dict):
					user_email = user_data.get("email") or user_data.get("id")
					if user_email:
						user_email = _ensure_user_from_mobile_data(
							email=user_email,
							name=user_data.get("name"),
							profile_pic=user_data.get("profile_pic"),
							user_id=user_data.get("id")
						)
						if user_email and user_email not in users_to_assign:
							users_to_assign.append(user_email)
				elif isinstance(user_data, str):
					if user_data and user_data not in users_to_assign:
						users_to_assign.append(user_data)
	
	# Ensure all items in users_to_assign are strings (not lists)
	users_to_assign = [u for u in users_to_assign if isinstance(u, str) and u]
	
	# Assign lead to all users via ToDo records
	# Set assigned_date when assigning users (will also be set by ToDo hook, but set it here too for immediate update)
	if users_to_assign:
		# Check if assigned_date is already set
		current_assigned_date = frappe.db.get_value("CRM Lead", lead_doc.name, "assigned_date")
		if not current_assigned_date:
			# Use db.set_value for direct database update
			frappe.db.set_value("CRM Lead", lead_doc.name, "assigned_date", today())
			frappe.db.commit()
	
	for user_email in users_to_assign:
		try:
			assign_task({
				"doctype": "CRM Lead",
				"name": lead_doc.name,
				"assign_to": [user_email],
				"description": lead_doc.lead_name or lead_doc.organization or lead_doc.email or "",
			})
		except Exception as e:
			frappe.log_error(f"Failed to assign lead {lead_doc.name} to {user_email}: {str(e)}", "Lead Assignment Error")
	
	frappe.db.commit()
	
	# Return full lead with all fields
	return get_compact_lead(lead_doc, return_all_fields=True)


@frappe.whitelist()
def edit_lead(lead_id=None, name=None, lead_name=None, first_name=None, last_name=None, middle_name=None,
			 email=None, mobile_no=None, phone=None, organization=None,
			 status=None, source=None, industry=None, lead_owner=None,
			 project=None, project_unit=None, single_unit=None,
			 job_title=None, website=None, territory=None,
			 assigned_to=None, assigned_to_list=None,
			 comment=None, comment_content=None,
			 **kwargs):
	"""
	Edit an existing CRM Lead.
	
	Args:
		lead_id: Lead ID (name) - required (can also use 'name')
		name: Lead name (alias for lead_id)
		... (same fields as create_lead)
		comment: Comment content to add after updating the lead (alias for comment_content)
		comment_content: Comment content to add after updating the lead
	
	Returns:
		Updated full lead JSON with all fields
	"""
	# Accept either lead_id or name
	lead_name_param = lead_id or name
	if not lead_name_param:
		frappe.throw(_("Lead ID is required"))
	
	name = lead_name_param
	
	# Get lead (this respects permissions)
	lead = frappe.get_doc("CRM Lead", name)
	
	# Get CRM Lead meta to validate fields
	lead_meta = frappe.get_meta("CRM Lead")
	valid_fields = {f.fieldname for f in lead_meta.fields}
	
	# Update standard fields if provided
	if lead_name is not None:
		lead.lead_name = lead_name
	if first_name is not None:
		lead.first_name = first_name
	if last_name is not None:
		lead.last_name = last_name
	if middle_name is not None:
		lead.middle_name = middle_name
	if email is not None:
		lead.email = email
	if mobile_no is not None:
		lead.mobile_no = mobile_no
	if phone is not None:
		lead.phone = phone
	if organization is not None:
		lead.organization = organization
	if job_title is not None:
		lead.job_title = job_title
	if website is not None:
		lead.website = website
	if territory is not None:
		lead.territory = territory
	
	# Handle link fields (with name resolution)
	if status is not None:
		if frappe.db.exists("CRM Lead Status", status):
			lead.status = status
		else:
			status_doc = frappe.get_all("CRM Lead Status", filters={"lead_status": status}, fields=["name"], limit=1)
			if status_doc:
				lead.status = status_doc[0].name
	
	if source is not None:
		if frappe.db.exists("CRM Lead Source", source):
			lead.source = source
		else:
			source_doc = frappe.get_all("CRM Lead Source", filters={"source_name": source}, fields=["name"], limit=1)
			if source_doc:
				lead.source = source_doc[0].name
			else:
				frappe.throw(_("Cannot find Source: {0}").format(source))
	
	if industry is not None:
		if frappe.db.exists("CRM Industry", industry):
			lead.industry = industry
		else:
			industry_doc = frappe.get_all("CRM Industry", filters={"industry_name": industry}, fields=["name"], limit=1)
			if industry_doc:
				lead.industry = industry_doc[0].name
			else:
				frappe.throw(_("Cannot find Industry: {0}").format(industry))
	
	if lead_owner is not None:
		# Lead owner is a User - check if it's email or name
		if frappe.db.exists("User", lead_owner):
			lead.lead_owner = lead_owner
		else:
			# Try to find by email
			user = frappe.get_all("User", filters={"email": lead_owner}, fields=["name"], limit=1)
			if user:
				lead.lead_owner = user[0].name
			else:
				frappe.throw(_("Cannot find User: {0}").format(lead_owner))
	
	if project is not None:
		if frappe.db.exists("Real Estate Project", project):
			lead.project = project
		else:
			project_doc = frappe.get_all("Real Estate Project", filters={"project_name": project}, fields=["name"], limit=1)
			if project_doc:
				lead.project = project_doc[0].name
			else:
				frappe.throw(_("Cannot find Project: {0}").format(project))
	
	if project_unit is not None:
		if frappe.db.exists("Project Unit", project_unit):
			lead.project_unit = project_unit
		else:
			unit_doc = frappe.get_all("Project Unit", filters={"unit_name": project_unit}, fields=["name"], limit=1)
			if unit_doc:
				lead.project_unit = unit_doc[0].name
			else:
				frappe.throw(_("Cannot find Project Unit: {0}").format(project_unit))
	
	if single_unit is not None:
		if frappe.db.exists("Unit", single_unit):
			lead.single_unit = single_unit
		else:
			unit_doc = frappe.get_all("Unit", filters={"unit_name": single_unit}, fields=["name"], limit=1)
			if unit_doc:
				lead.single_unit = unit_doc[0].name
			else:
				frappe.throw(_("Cannot find Unit: {0}").format(single_unit))
	
	# Update any other valid fields from kwargs
	for key, value in kwargs.items():
		if key in valid_fields and hasattr(lead, key) and value is not None:
			setattr(lead, key, value)
	
	# Save lead
	lead.save()
	frappe.db.commit()
	
	# Handle assigned_to_list (multiple users via Frappe's assign_to system)
	# Check if assigned_to is a list (mobile app might send list instead of assigned_to_list)
	assigned_to_is_list = False
	if assigned_to is not None:
		if isinstance(assigned_to, list):
			# If assigned_to is a list, treat it as assigned_to_list
			assigned_to_is_list = True
			if assigned_to_list is None:
				assigned_to_list = assigned_to
	
	# Handle assigned_to_list (multiple users via Frappe's assign_to system)
	users_to_assign = []
	
	# Process assigned_to_list first
	if assigned_to_list is not None:
		if isinstance(assigned_to_list, str):
			try:
				assigned_to_list = frappe.parse_json(assigned_to_list)
			except:
				assigned_to_list = [assigned_to_list]
		
		if isinstance(assigned_to_list, list):
			for user_data in assigned_to_list:
				if isinstance(user_data, dict):
					# Extract email from user object
					user_email = user_data.get("email") or user_data.get("id")
					if user_email:
						# Ensure user exists from mobile data
						user_email = _ensure_user_from_mobile_data(
							email=user_email,
							name=user_data.get("name"),
							profile_pic=user_data.get("profile_pic"),
							user_id=user_data.get("id")
						)
						if user_email and user_email not in users_to_assign:
							users_to_assign.append(user_email)
				elif isinstance(user_data, str):
					# Direct email string
					if user_data and user_data not in users_to_assign:
						users_to_assign.append(user_data)
	
	# Also add single assigned_to if provided (only if it's a string, not a list)
	# If assigned_to was a list, it was already converted to assigned_to_list above
	if assigned_to and not assigned_to_is_list:
		if isinstance(assigned_to, str):
			if assigned_to not in users_to_assign:
				users_to_assign.append(assigned_to)
		elif isinstance(assigned_to, list):
			# Handle list of dicts (like mobile app sends)
			for user_data in assigned_to:
				if isinstance(user_data, dict):
					user_email = user_data.get("email") or user_data.get("id")
					if user_email:
						user_email = _ensure_user_from_mobile_data(
							email=user_email,
							name=user_data.get("name"),
							profile_pic=user_data.get("profile_pic"),
							user_id=user_data.get("id")
						)
						if user_email and user_email not in users_to_assign:
							users_to_assign.append(user_email)
				elif isinstance(user_data, str):
					if user_data and user_data not in users_to_assign:
						users_to_assign.append(user_data)
	
	# Ensure all items in users_to_assign are strings (not lists)
	users_to_assign = [u for u in users_to_assign if isinstance(u, str) and u]
	
	# Update assignments: remove old ones and add new ones
	if assigned_to_list is not None or assigned_to is not None:
		# Get current assigned users
		current_todos = frappe.get_all(
			"ToDo",
			filters={
				"reference_type": "CRM Lead",
				"reference_name": lead.name,
				"status": "Open"
			},
			fields=["allocated_to"],
			distinct=True
		)
		current_users = {todo.allocated_to for todo in current_todos if todo.allocated_to}
		
		# Remove users not in new list
		users_to_remove = current_users - set(users_to_assign)
		for user_email in users_to_remove:
			try:
				unassign_task("CRM Lead", lead.name, user_email)
			except Exception as e:
				frappe.log_error(f"Failed to unassign lead {lead.name} from {user_email}: {str(e)}", "Lead Unassignment Error")
		
		# Add new users
		users_to_add = set(users_to_assign) - current_users
		
		# Set assigned_date when adding new users (if not already set)
		# Will also be set by ToDo hook, but set it here too for immediate update
		if users_to_add:
			current_assigned_date = frappe.db.get_value("CRM Lead", lead.name, "assigned_date")
			if not current_assigned_date:
				# Use db.set_value for direct database update
				frappe.db.set_value("CRM Lead", lead.name, "assigned_date", today())
				frappe.db.commit()
		
		for user_email in users_to_add:
			try:
				assign_task({
					"doctype": "CRM Lead",
					"name": lead.name,
					"assign_to": [user_email],
					"description": lead.lead_name or lead.organization or lead.email or "",
				})
			except Exception as e:
				frappe.log_error(f"Failed to assign lead {lead.name} to {user_email}: {str(e)}", "Lead Assignment Error")
	
	frappe.db.commit()
	
	# Handle comment (if provided)
	comment_text = comment or comment_content
	if comment_text and str(comment_text).strip():
		try:
			from frappe.desk.form.utils import add_comment
			# Get current user info for comment
			user = frappe.session.user
			user_doc = frappe.get_doc("User", user)
			comment_email = user_doc.email or user
			comment_by = user_doc.full_name or user_doc.name or user
			
			add_comment(
				reference_doctype="CRM Lead",
				reference_name=lead.name,
				content=str(comment_text).strip(),
				comment_email=comment_email,
				comment_by=comment_by
			)
			frappe.db.commit()
		except Exception as e:
			# Log error but don't fail the lead update
			frappe.log_error(f"Error adding comment to lead {lead.name}: {str(e)}", "edit_lead_comment_error")
	
	# Return full lead with all fields
	return get_compact_lead(lead, return_all_fields=True)


@frappe.whitelist()
def update_lead(lead_id=None, name=None, lead_name=None, first_name=None, last_name=None, middle_name=None,
			   email=None, mobile_no=None, phone=None, organization=None,
			   status=None, source=None, industry=None, lead_owner=None,
			   project=None, project_unit=None, single_unit=None,
			   job_title=None, website=None, territory=None,
			   assigned_to=None, assigned_to_list=None,
			   comment=None, comment_content=None,
			   **kwargs):
	"""
	Alias for edit_lead - Update an existing CRM Lead.
	This function is provided for compatibility with mobile apps that use 'update_lead' endpoint.
	
	See edit_lead() for full documentation.
	"""
	return edit_lead(
		lead_id=lead_id, name=name, lead_name=lead_name, first_name=first_name,
		last_name=last_name, middle_name=middle_name, email=email,
		mobile_no=mobile_no, phone=phone, organization=organization,
		status=status, source=source, industry=industry, lead_owner=lead_owner,
		project=project, project_unit=project_unit, single_unit=single_unit,
		job_title=job_title, website=website, territory=territory,
		assigned_to=assigned_to, assigned_to_list=assigned_to_list,
		comment=comment, comment_content=comment_content,
		**kwargs
	)


@frappe.whitelist()
def delete_lead(lead_id=None, name=None):
	"""
	Delete a CRM Lead.
	Deletes linked documents (ToDo, Notification Log, Comments) first to avoid link errors.
	
	Args:
		lead_id: Lead ID (name) - required (can also use 'name')
		name: Lead name (alias for lead_id)
	
	Returns:
		Success message
	"""
	# Accept either lead_id or name
	lead_name = lead_id or name
	if not lead_name:
		frappe.throw(_("Lead ID is required"))
	
	# Check if lead exists
	if not frappe.db.exists("CRM Lead", lead_name):
		frappe.throw(_("Lead {0} does not exist").format(lead_name))
	
	# Delete linked documents first to avoid link errors
	# 1. Delete ToDo records
	todos = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": "CRM Lead",
			"reference_name": lead_name
		},
		fields=["name"]
	)
	for todo in todos:
		try:
			frappe.delete_doc("ToDo", todo.name, ignore_permissions=True, force=True)
		except Exception as e:
			frappe.log_error(f"Error deleting ToDo {todo.name}: {str(e)}", "Delete Lead Error")
	
	# 2. Delete Notification Log records (dynamic link)
	# Note: Notification Log uses fields document_type & document_name (not for_doctype)
	notification_logs = frappe.get_all(
		"Notification Log",
		filters={
			"document_type": "CRM Lead",
			"document_name": lead_name
		},
		fields=["name"]
	)
	for notif in notification_logs:
		try:
			frappe.delete_doc("Notification Log", notif.name, ignore_permissions=True, force=True)
		except Exception as e:
			frappe.log_error(f"Error deleting Notification Log {notif.name}: {str(e)}", "Delete Lead Error")
	
	# 3. Delete Comments
	comments = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": "CRM Lead",
			"reference_name": lead_name
		},
		fields=["name"]
	)
	for comment in comments:
		try:
			frappe.delete_doc("Comment", comment.name, ignore_permissions=True, force=True)
		except Exception as e:
			frappe.log_error(f"Error deleting Comment {comment.name}: {str(e)}", "Delete Lead Error")
	
	# 4. Delete DocShare records
	docshares = frappe.get_all(
		"DocShare",
		filters={
			"share_doctype": "CRM Lead",
			"share_name": lead_name
		},
		fields=["name"]
	)
	for docshare in docshares:
		try:
			frappe.delete_doc("DocShare", docshare.name, ignore_permissions=True, force=True)
		except Exception as e:
			frappe.log_error(f"Error deleting DocShare {docshare.name}: {str(e)}", "Delete Lead Error")
	
	# 5. Delete CRM Notification records (dynamic link)
	if frappe.db.table_exists("CRM Notification"):
		crm_notifications = frappe.get_all(
			"CRM Notification",
			filters={
				"reference_doctype": "CRM Lead",
				"reference_name": lead_name
			},
			fields=["name"]
		)
		for notif in crm_notifications:
			try:
				frappe.delete_doc("CRM Notification", notif.name, ignore_permissions=True, force=True)
			except Exception as e:
				frappe.log_error(f"Error deleting CRM Notification {notif.name}: {str(e)}", "Delete Lead Error")
	
	# Commit deletions
	frappe.db.commit()
	
	# Now delete the lead itself
	try:
		lead = frappe.get_doc("CRM Lead", lead_name)
		lead.delete(ignore_permissions=True)
		frappe.db.commit()
	except Exception as e:
		# If still fails, try with force
		try:
			frappe.delete_doc("CRM Lead", lead_name, ignore_permissions=True, force=True)
			frappe.db.commit()
		except Exception as e2:
			frappe.log_error(f"Error deleting Lead {lead_name}: {str(e2)}", "Delete Lead Error")
			frappe.throw(_("Failed to delete Lead {0}: {1}").format(lead_name, str(e2)))
	
	return {
		"message": _("Lead {0} deleted successfully").format(lead_name),
		"deleted": True,
		"lead_id": lead_name
	}


@frappe.whitelist()
def get_all_leads(page=1, limit=20, order_by="modified desc",
				  # Filter parameters for all CRM Lead fields
				  status=None, source=None, industry=None,
				  lead_name=None, first_name=None, last_name=None, middle_name=None,
				  email=None, mobile_no=None, phone=None,
				  organization=None, job_title=None, website=None,
				  lead_owner=None, assigned_to=None,
				  project=None, project_unit=None, single_unit=None,
				  territory=None, campaign=None,
				  converted=None, delayed=None, assigned_date=None,
				  creation_from=None, creation_to=None,
				  modified_from=None, modified_to=None,
				  budget_from=None, budget_to=None,
				  space_from=None, space_to=None,
				  best_time_contacte_from=None, best_time_contacte_to=None,
				  **kwargs):
	"""
	Get all CRM Leads with pagination and filtering on all fields.
	Returns all available fields for each lead.
	
	Args:
		page: Page number (1-based, default: 1)
		limit: Number of leads per page (default: 20)
		order_by: Sort order (default: "modified desc")
		
		# Filter parameters (all optional):
		status: Status filter (string or comma-separated: "New,Contacted,Qualified")
		source: Source filter (string or comma-separated)
		industry: Industry filter (string or comma-separated)
		lead_name: Full name text search (partial match)
		first_name: First name text search (partial match)
		last_name: Last name text search (partial match)
		middle_name: Middle name text search (partial match)
		email: Email text search (partial match)
		mobile_no: Mobile number text search (partial match)
		phone: Phone text search (partial match)
		organization: Organization text search (partial match)
		job_title: Job title text search (partial match)
		website: Website text search (partial match)
		lead_owner: Lead owner (User name or email)
		assigned_to: Assigned user email or name
		project: Project name or ID
		project_unit: Project Unit name or ID
		single_unit: Single Unit name or ID
		territory: Territory name or ID
		campaign: Campaign name or ID
		converted: Converted filter (0 or 1)
		delayed: Delayed filter (0 or 1)
		assigned_date: Assigned date filter (YYYY-MM-DD)
		creation_from: Creation date filter from (YYYY-MM-DD or DD-MM-YYYY)
		creation_to: Creation date filter to (YYYY-MM-DD or DD-MM-YYYY)
		modified_from: Modified date filter from (YYYY-MM-DD or DD-MM-YYYY)
		modified_to: Modified date filter to (YYYY-MM-DD or DD-MM-YYYY)
		budget_from: Budget filter from (minimum value)
		budget_to: Budget filter to (maximum value)
		space_from: Space filter from (minimum value in square meters)
		space_to: Space filter to (maximum value in square meters)
		best_time_contacte_from: Best time to contact filter from (HH:MM:SS format, hours only)
		best_time_contacte_to: Best time to contact filter to (HH:MM:SS format, hours only)
	
	Returns:
		{
			"message": {
				"data": [leads...],
				"page": current_page,
				"page_size": limit,
				"total": total_leads,
				"total_pages": total_pages,
				"has_next": boolean,
				"has_previous": boolean
			}
		}
	"""
	# Get parameters from form_dict for GET requests
	if hasattr(frappe, 'form_dict') and frappe.form_dict:
		# Override with form_dict values (query string takes precedence)
		status = frappe.form_dict.get('status') if 'status' in frappe.form_dict else status
		source = frappe.form_dict.get('source') if 'source' in frappe.form_dict else source
		industry = frappe.form_dict.get('industry') if 'industry' in frappe.form_dict else industry
		lead_name = frappe.form_dict.get('lead_name') if 'lead_name' in frappe.form_dict else lead_name
		first_name = frappe.form_dict.get('first_name') if 'first_name' in frappe.form_dict else first_name
		last_name = frappe.form_dict.get('last_name') if 'last_name' in frappe.form_dict else last_name
		middle_name = frappe.form_dict.get('middle_name') if 'middle_name' in frappe.form_dict else middle_name
		email = frappe.form_dict.get('email') if 'email' in frappe.form_dict else email
		mobile_no = frappe.form_dict.get('mobile_no') if 'mobile_no' in frappe.form_dict else mobile_no
		phone = frappe.form_dict.get('phone') if 'phone' in frappe.form_dict else phone
		organization = frappe.form_dict.get('organization') if 'organization' in frappe.form_dict else organization
		job_title = frappe.form_dict.get('job_title') if 'job_title' in frappe.form_dict else job_title
		website = frappe.form_dict.get('website') if 'website' in frappe.form_dict else website
		lead_owner = frappe.form_dict.get('lead_owner') if 'lead_owner' in frappe.form_dict else lead_owner
		assigned_to = frappe.form_dict.get('assigned_to') if 'assigned_to' in frappe.form_dict else assigned_to
		project = frappe.form_dict.get('project') if 'project' in frappe.form_dict else project
		project_unit = frappe.form_dict.get('project_unit') if 'project_unit' in frappe.form_dict else project_unit
		single_unit = frappe.form_dict.get('single_unit') if 'single_unit' in frappe.form_dict else single_unit
		territory = frappe.form_dict.get('territory') if 'territory' in frappe.form_dict else territory
		campaign = frappe.form_dict.get('campaign') if 'campaign' in frappe.form_dict else campaign
		converted = frappe.form_dict.get('converted') if 'converted' in frappe.form_dict else converted
		delayed = frappe.form_dict.get('delayed') if 'delayed' in frappe.form_dict else delayed
		assigned_date = frappe.form_dict.get('assigned_date') if 'assigned_date' in frappe.form_dict else assigned_date
		creation_from = frappe.form_dict.get('creation_from') if 'creation_from' in frappe.form_dict else creation_from
		creation_to = frappe.form_dict.get('creation_to') if 'creation_to' in frappe.form_dict else creation_to
		modified_from = frappe.form_dict.get('modified_from') if 'modified_from' in frappe.form_dict else modified_from
		modified_to = frappe.form_dict.get('modified_to') if 'modified_to' in frappe.form_dict else modified_to
		budget_from = frappe.form_dict.get('budget_from') if 'budget_from' in frappe.form_dict else budget_from
		budget_to = frappe.form_dict.get('budget_to') if 'budget_to' in frappe.form_dict else budget_to
		space_from = frappe.form_dict.get('space_from') if 'space_from' in frappe.form_dict else space_from
		space_to = frappe.form_dict.get('space_to') if 'space_to' in frappe.form_dict else space_to
		best_time_contacte_from = frappe.form_dict.get('best_time_contacte_from') if 'best_time_contacte_from' in frappe.form_dict else best_time_contacte_from
		best_time_contacte_to = frappe.form_dict.get('best_time_contacte_to') if 'best_time_contacte_to' in frappe.form_dict else best_time_contacte_to
		page = frappe.form_dict.get('page') if 'page' in frappe.form_dict else page
		limit = frappe.form_dict.get('limit') if 'limit' in frappe.form_dict else limit
		order_by = frappe.form_dict.get('order_by') if 'order_by' in frappe.form_dict else order_by
	
	page = cint(page) or 1
	limit = cint(limit) or 20
	
	if page < 1:
		page = 1
	if limit < 1:
		limit = 20
	if limit > 100:
		limit = 100  # Cap at 100 for performance
	
	# Calculate offset
	start = (page - 1) * limit
	
	# Build filters dynamically
	filters = []
	
	# Status filter
	if status and str(status).strip():
		statuses = [s.strip() for s in status.split(",") if s.strip()]
		if statuses:
			if len(statuses) == 1:
				filters.append(["status", "=", statuses[0]])
			else:
				filters.append(["status", "in", statuses])
	
	# Source filter
	if source and str(source).strip():
		sources = [s.strip() for s in source.split(",") if s.strip()]
		if sources:
			if len(sources) == 1:
				filters.append(["source", "=", sources[0]])
			else:
				filters.append(["source", "in", sources])
	
	# Industry filter
	if industry and str(industry).strip():
		industries = [i.strip() for i in industry.split(",") if i.strip()]
		if industries:
			if len(industries) == 1:
				filters.append(["industry", "=", industries[0]])
			else:
				filters.append(["industry", "in", industries])
	
	# Text search filters (partial match)
	if lead_name and str(lead_name).strip():
		filters.append(["lead_name", "like", f"%{lead_name}%"])
	if first_name and str(first_name).strip():
		filters.append(["first_name", "like", f"%{first_name}%"])
	if last_name and str(last_name).strip():
		filters.append(["last_name", "like", f"%{last_name}%"])
	if middle_name and str(middle_name).strip():
		filters.append(["middle_name", "like", f"%{middle_name}%"])
	if email and str(email).strip():
		filters.append(["email", "like", f"%{email}%"])
	if mobile_no and str(mobile_no).strip():
		filters.append(["mobile_no", "like", f"%{mobile_no}%"])
	if phone and str(phone).strip():
		filters.append(["phone", "like", f"%{phone}%"])
	if organization and str(organization).strip():
		filters.append(["organization", "like", f"%{organization}%"])
	if job_title and str(job_title).strip():
		filters.append(["job_title", "like", f"%{job_title}%"])
	if website and str(website).strip():
		filters.append(["website", "like", f"%{website}%"])
	
	# Link field filters (support names or IDs)
	if lead_owner and str(lead_owner).strip():
		# Try to resolve user name/email to user ID
		try:
			user = frappe.db.get_value("User", {"email": lead_owner}, "name") or frappe.db.get_value("User", lead_owner, "name")
			if user:
				filters.append(["lead_owner", "=", user])
		except:
			filters.append(["lead_owner", "=", lead_owner])
	
	if assigned_to and str(assigned_to).strip():
		# For assigned_to, we need to check ToDo records
		# This will be handled after getting leads
		pass
	
	# Project filters (support names or IDs)
	if project and str(project).strip():
		if frappe.db.exists("Real Estate Project", project):
			filters.append(["project", "=", project])
		else:
			project_doc = frappe.get_all("Real Estate Project", filters={"project_name": project}, fields=["name"], limit=1)
			if project_doc:
				filters.append(["project", "=", project_doc[0].name])
			else:
				filters.append(["project", "=", project])
	
	if project_unit and str(project_unit).strip():
		if frappe.db.exists("Project Unit", project_unit):
			filters.append(["project_unit", "=", project_unit])
		else:
			unit_doc = frappe.get_all("Project Unit", filters={"unit_name": project_unit}, fields=["name"], limit=1)
			if unit_doc:
				filters.append(["project_unit", "=", unit_doc[0].name])
			else:
				filters.append(["project_unit", "=", project_unit])
	
	if single_unit and str(single_unit).strip():
		if frappe.db.exists("Unit", single_unit):
			filters.append(["single_unit", "=", single_unit])
		else:
			unit_doc = frappe.get_all("Unit", filters={"unit_name": single_unit}, fields=["name"], limit=1)
			if unit_doc:
				filters.append(["single_unit", "=", unit_doc[0].name])
			else:
				filters.append(["single_unit", "=", single_unit])
	
	if territory and str(territory).strip():
		filters.append(["territory", "=", territory])
	
	if campaign and str(campaign).strip():
		filters.append(["campaign", "=", campaign])
	
	# Converted filter
	if converted is not None:
		converted_val = cint(converted)
		filters.append(["converted", "=", converted_val])
	
	# Delayed filter
	if delayed is not None:
		delayed_val = cint(delayed)
		filters.append(["delayed", "=", delayed_val])
	
	# Assigned date filter
	if assigned_date and str(assigned_date).strip():
		filters.append(["assigned_date", "=", assigned_date])
	
	# Helper function to normalize date format (DD-MM-YYYY to YYYY-MM-DD)
	def normalize_date(date_str):
		if not date_str:
			return None
		date_str = str(date_str).strip()
		if "-" in date_str:
			parts = date_str.split("-")
			if len(parts) == 3:
				try:
					part1 = int(parts[0])
					part2 = int(parts[1])
					part3 = int(parts[2])
					
					if part1 > 31:
						return date_str
					elif part1 <= 31 and part2 > 12:
						return f"{part3}-{part2:02d}-{part1:02d}"
					elif part1 > 12 and part2 <= 12:
						return f"{part3}-{part2:02d}-{part1:02d}"
					else:
						return date_str
				except ValueError:
					return date_str
		return date_str
	
	# Creation date filters
	if creation_from:
		creation_from = normalize_date(creation_from)
		if creation_from:
			if len(creation_from) == 10:
				filters.append(["creation", ">=", f"{creation_from} 00:00:00"])
			else:
				filters.append(["creation", ">=", creation_from])
	if creation_to:
		creation_to = normalize_date(creation_to)
		if creation_to:
			if len(creation_to) == 10:
				filters.append(["creation", "<=", f"{creation_to} 23:59:59"])
			else:
				filters.append(["creation", "<=", creation_to])
	
	# Modified date filters
	if modified_from:
		modified_from = normalize_date(modified_from)
		if modified_from:
			if len(modified_from) == 10:
				filters.append(["modified", ">=", f"{modified_from} 00:00:00"])
			else:
				filters.append(["modified", ">=", modified_from])
	if modified_to:
		modified_to = normalize_date(modified_to)
		if modified_to:
			if len(modified_to) == 10:
				filters.append(["modified", "<=", f"{modified_to} 23:59:59"])
			else:
				filters.append(["modified", "<=", modified_to])
	
	# Budget range filters
	if budget_from is not None and str(budget_from).strip():
		try:
			budget_from_val = float(budget_from)
			filters.append(["budget", ">=", budget_from_val])
		except (ValueError, TypeError):
			pass
	if budget_to is not None and str(budget_to).strip():
		try:
			budget_to_val = float(budget_to)
			filters.append(["budget", "<=", budget_to_val])
		except (ValueError, TypeError):
			pass
	
	# Space range filters
	if space_from is not None and str(space_from).strip():
		try:
			space_from_val = float(space_from)
			filters.append(["space", ">=", space_from_val])
		except (ValueError, TypeError):
			pass
	if space_to is not None and str(space_to).strip():
		try:
			space_to_val = float(space_to)
			filters.append(["space", "<=", space_to_val])
		except (ValueError, TypeError):
			pass
	
	# Best time to contact range filters (hours only)
	# best_time_contacte is stored as "HH:MM:SS" format
	if best_time_contacte_from and str(best_time_contacte_from).strip():
		time_from = str(best_time_contacte_from).strip()
		# Normalize time format: if only hours provided (e.g., "09"), convert to "09:00:00"
		if ":" not in time_from:
			try:
				hour = int(time_from)
				if 0 <= hour <= 23:
					time_from = f"{hour:02d}:00:00"
			except ValueError:
				pass
		# If format is "HH:MM", convert to "HH:MM:00"
		elif time_from.count(":") == 1:
			time_from = f"{time_from}:00"
		# Ensure format is "HH:MM:SS"
		if len(time_from) == 8 and time_from.count(":") == 2:
			filters.append(["best_time_contacte", ">=", time_from])
	if best_time_contacte_to and str(best_time_contacte_to).strip():
		time_to = str(best_time_contacte_to).strip()
		# Normalize time format: if only hours provided (e.g., "17"), convert to "17:59:59"
		if ":" not in time_to:
			try:
				hour = int(time_to)
				if 0 <= hour <= 23:
					time_to = f"{hour:02d}:59:59"
			except ValueError:
				pass
		# If format is "HH:MM", convert to "HH:MM:59"
		elif time_to.count(":") == 1:
			time_to = f"{time_to}:59"
		# Ensure format is "HH:MM:SS"
		if len(time_to) == 8 and time_to.count(":") == 2:
			filters.append(["best_time_contacte", "<=", time_to])
	
	# Helper function to get member user column
	def _get_member_user_col():
		try:
			meta = frappe.get_meta("Member", cached=True)
			for f in meta.get("fields", []):
				if getattr(f, "fieldtype", None) == "Link" and getattr(f, "options", None) == "User":
					return "Member", f.fieldname
			for alt in ("user", "member", "user_id", "user_email", "allocated_to"):
				if meta.get_field(alt):
					return "Member", alt
		except Exception:
			pass
		return "Member", "user"
	
	# Apply user-based permission filtering
	# Each user should only see leads they own, assigned to them, or assigned to their team
	current_user = frappe.session.user
	if current_user and current_user != "Guest":
		user_roles = set(frappe.get_roles(current_user))
		
		# System Manager can see all leads (no additional filtering)
		if "System Manager" not in user_roles:
			# Build permission filters: owner OR assigned_to OR assigned_to_team
			permission_filters = []
			
			# 1. Owner filter
			permission_filters.append(["owner", "=", current_user])
			
			# 2. Assigned to current user (via ToDo)
			# Get all leads assigned to current user
			assigned_leads = frappe.get_all(
				"ToDo",
				filters=[
					["reference_type", "=", "CRM Lead"],
					["allocated_to", "=", current_user],
					["status", "=", "Open"]
				],
				fields=["reference_name"],
				pluck="reference_name"
			)
			
			# 3. Assigned to team members (if user is Team Leader)
			# Get team members
			member_dt, member_col = _get_member_user_col()
			team_members = frappe.db.sql_list(
				f"""
				SELECT DISTINCT m.`{member_col}`
				FROM `tab{member_dt}` m
				JOIN `tabTeam` t ON m.`parent` = t.`name`
				WHERE t.`team_leader` = %s
				""",
				(current_user,),
			) or []
			
			# Get leads assigned to team members
			team_assigned_leads = []
			if team_members:
				team_assigned_leads = frappe.get_all(
					"ToDo",
					filters=[
						["reference_type", "=", "CRM Lead"],
						["allocated_to", "in", team_members],
						["status", "=", "Open"]
					],
					fields=["reference_name"],
					pluck="reference_name"
				)
			
			# Combine all allowed lead names (assigned + team)
			allowed_lead_names = set(assigned_leads + team_assigned_leads)
			
			# Build permission filter: owner = current_user OR name in allowed_leads
			# We'll use a more efficient approach by getting owned leads and combining
			if allowed_lead_names:
				# Get owned leads and combine with assigned/team leads
				owned_leads = frappe.get_all(
					"CRM Lead",
					filters=[["owner", "=", current_user]],
					fields=["name"],
					pluck="name"
				)
				# Combine all allowed lead names
				allowed_lead_names.update(owned_leads)
				
				# Add filter to only include allowed leads
				# This efficiently combines owner + assigned + team in one filter
				filters.append(["name", "in", list(allowed_lead_names)])
			else:
				# No assigned/team leads, only show owned leads
				filters.append(["owner", "=", current_user])
	
	# Get total count with filters
	total = frappe.db.count("CRM Lead", filters=filters if filters else None)
	
	# Get all fields from CRM Lead doctype (use "*" to get all fields automatically)
	# This ensures all fields including custom fields are returned
	meta = frappe.get_meta("CRM Lead")
	all_fieldnames = [f.fieldname for f in meta.fields 
	                  if f.fieldtype not in ['Tab Break', 'Section Break', 'Column Break', 'Table']]
	
	# Ensure 'name' field is always included (it's a system field)
	if 'name' not in all_fieldnames:
		all_fieldnames.insert(0, 'name')
	
	# Use _safe_fields to filter out any problematic fields
	fields = _safe_fields("CRM Lead", all_fieldnames)
	
	# Get leads with pagination (same approach as get_all_tasks)
	leads = frappe.get_all(
		"CRM Lead",
		filters=filters if filters else None,
		fields=fields,
		order_by=order_by,
		limit_start=start,
		limit_page_length=limit
	)
	
	# Format leads using compact helper
	data = [get_compact_lead(lead, return_all_fields=True) for lead in leads]
	
	# Filter by assigned_to if specified (check ToDo records)
	if assigned_to and str(assigned_to).strip():
		try:
			# Resolve user email/name to user ID
			user = frappe.db.get_value("User", {"email": assigned_to}, "name") or frappe.db.get_value("User", assigned_to, "name")
			if user:
				# Get leads assigned to this user via ToDo
				todo_leads = frappe.get_all(
					"ToDo",
					filters=[
						["reference_type", "=", "CRM Lead"],
						["allocated_to", "=", user],
						["status", "!=", "Cancelled"]
					],
					fields=["reference_name"],
					pluck="reference_name"
				)
				# Filter data to only include leads assigned to this user
				data = [lead for lead in data if lead.get("name") in todo_leads]
				# Recalculate total for assigned_to filter
				total = len(data)
		except Exception as e:
			frappe.log_error(f"Error filtering by assigned_to: {str(e)}", "get_all_leads_assigned_to_error")
	
	# Get all comments and last comment for each lead
	if data:
		try:
			lead_names = [lead.get("name") for lead in data if lead.get("name")]
			if lead_names:
				# Get all comments for each lead (with all available fields)
				all_comments = frappe.get_all(
					"Comment",
					filters=[
						["reference_doctype", "=", "CRM Lead"],
						["reference_name", "in", lead_names],
						["comment_type", "=", "Comment"]
					],
					fields=["name", "reference_name", "reference_doctype", "reference_owner",
					        "comment_type", "comment_email", "comment_by", "subject",
					        "content", "creation", "modified", "published", "seen",
					        "delayed", "ip_address"],
					order_by="creation desc"
				)
				
				# Create dictionaries mapping lead_name to comments
				last_comments = {}  # Last comment only
				all_comments_dict = {}  # All comments grouped by lead
				
				for comment in all_comments:
					lead_name = comment.get("reference_name")
					if lead_name:
						# Format comment data with all fields
						comment_data = {
							"name": comment.get("name"),
							"reference_name": comment.get("reference_name"),
							"reference_doctype": comment.get("reference_doctype"),
							"reference_owner": comment.get("reference_owner"),
							"comment_type": comment.get("comment_type"),
							"comment_email": comment.get("comment_email"),
							"comment_by": comment.get("comment_by"),
							"subject": comment.get("subject"),
							"content": comment.get("content"),
							"creation": comment.get("creation"),
							"modified": comment.get("modified"),
							"published": comment.get("published"),
							"seen": comment.get("seen"),
							"delayed": comment.get("delayed"),
							"ip_address": comment.get("ip_address")
						}
						
						# Store last comment (first one encountered is the most recent due to order_by)
						if lead_name not in last_comments:
							last_comments[lead_name] = comment_data
						
						# Store all comments
						if lead_name not in all_comments_dict:
							all_comments_dict[lead_name] = []
						all_comments_dict[lead_name].append(comment_data)
				
				# Add last_comment and comments to each lead in data
				for lead in data:
					lead_name = lead.get("name")
					# Always add comments fields, even if lead_name is None
					if lead_name and lead_name in last_comments:
						lead["last_comment"] = last_comments[lead_name]
					else:
						lead["last_comment"] = None
					
					if lead_name and lead_name in all_comments_dict:
						# Sort comments by creation desc (newest first)
						lead["comments"] = sorted(
							all_comments_dict[lead_name],
							key=lambda x: x.get("creation", ""),
							reverse=True
						)
					else:
						lead["comments"] = []
		except Exception as e:
			frappe.log_error(f"Error fetching comments: {str(e)}", "get_all_leads_comments_error")
			# If error occurs, set last_comment and comments to None/empty for all leads
			for lead in data:
				lead["last_comment"] = None
				lead["comments"] = []
	
	# Add Table fields (child tables) for each lead
	if data:
		try:
			lead_names = [lead.get("name") for lead in data if lead.get("name")]
			if lead_names:
				# Get duplicate_leads table data
				duplicate_leads_data = frappe.get_all(
					"Duplicate Lead Entry",
					filters=[["parent", "in", lead_names]],
					fields=["parent", "name", "lead", "lead_name", "email", "mobile_no"],
					order_by="parent, idx"
				)
				duplicate_leads_dict = {}
				for row in duplicate_leads_data:
					parent = row.get("parent")
					if parent not in duplicate_leads_dict:
						duplicate_leads_dict[parent] = []
					duplicate_leads_dict[parent].append({
						"name": row.get("name"),
						"lead": row.get("lead"),
						"lead_name": row.get("lead_name"),
						"email": row.get("email"),
						"mobile_no": row.get("mobile_no")
					})
				
				# Get status_change_log table data
				status_change_log_data = frappe.get_all(
					"CRM Status Change Log",
					filters=[["parent", "in", lead_names]],
					fields=["parent", "name", "from_status", "to_status", "changed_by", "changed_on", "reason"],
					order_by="parent, idx"
				)
				status_change_log_dict = {}
				for row in status_change_log_data:
					parent = row.get("parent")
					if parent not in status_change_log_dict:
						status_change_log_dict[parent] = []
					status_change_log_dict[parent].append({
						"name": row.get("name"),
						"from_status": row.get("from_status"),
						"to_status": row.get("to_status"),
						"changed_by": row.get("changed_by"),
						"changed_on": row.get("changed_on"),
						"reason": row.get("reason")
					})
				
				# Get property_preference_details table data
				property_preference_data = frappe.get_all(
					"Property Preference",
					filters=[["parent", "in", lead_names]],
					fields=["parent", "name", "*"],
					order_by="parent, idx"
				)
				property_preference_dict = {}
				for row in property_preference_data:
					parent = row.get("parent")
					if parent not in property_preference_dict:
						property_preference_dict[parent] = []
					# Remove parent and doctype from row data
					row_data = {k: v for k, v in row.items() if k not in ["parent", "doctype"]}
					property_preference_dict[parent].append(row_data)
				
				# Get products table data
				products_data = frappe.get_all(
					"CRM Products",
					filters=[["parent", "in", lead_names]],
					fields=["parent", "name", "*"],
					order_by="parent, idx"
				)
				products_dict = {}
				for row in products_data:
					parent = row.get("parent")
					if parent not in products_dict:
						products_dict[parent] = []
					# Remove parent and doctype from row data
					row_data = {k: v for k, v in row.items() if k not in ["parent", "doctype"]}
					products_dict[parent].append(row_data)
				
				# Add table fields to each lead
				for lead in data:
					lead_name = lead.get("name")
					if lead_name:  # Only process if lead_name is not None
						lead["duplicate_leads"] = duplicate_leads_dict.get(lead_name, [])
						lead["status_change_log"] = status_change_log_dict.get(lead_name, [])
						lead["property_preference_details"] = property_preference_dict.get(lead_name, [])
						lead["products"] = products_dict.get(lead_name, [])
					else:
						# If lead_name is None, set empty arrays
						lead["duplicate_leads"] = []
						lead["status_change_log"] = []
						lead["property_preference_details"] = []
						lead["products"] = []
		except Exception as e:
			frappe.log_error(f"Error fetching table fields: {str(e)}", "get_all_leads_table_fields_error")
			# If error occurs, set table fields to empty arrays for all leads
			for lead in data:
				lead["duplicate_leads"] = []
				lead["status_change_log"] = []
				lead["property_preference_details"] = []
				lead["products"] = []
	
	# Calculate pagination info
	total_pages = (total + limit - 1) // limit if total > 0 else 0
	has_next = (start + len(data)) < total
	has_previous = page > 1
	
	return {
		"message": {
			"data": data,
			"page": page,
			"page_size": limit,
			"total": total,
			"total_pages": total_pages,
			"has_next": has_next,
			"has_previous": has_previous
		}
	}


@frappe.whitelist()
def get_all_comments(page=1, limit=None, order_by="creation desc",
					 # Filter parameters for Comment fields
					 comment_type=None, comment_email=None, comment_by=None,
					 reference_doctype=None, reference_name=None, reference_owner=None,
					 subject=None, content=None, published=None, seen=None,
					 delayed=None, ip_address=None,
					 creation_from=None, creation_to=None,
					 modified_from=None, modified_to=None,
					 **kwargs):
	"""
	Get all Comments with pagination and filtering on all fields.
	Returns all available fields for each comment.
	
	Args:
		page: Page number (1-based, default: 1)
		limit: Number of comments per page (default: 20)
		order_by: Sort order (default: "creation desc")
		
		# Filter parameters (all optional):
		comment_type: Comment type filter (string or comma-separated: "Comment,Like,Share")
		comment_email: Comment email filter (text search)
		comment_by: Comment by filter (text search)
		reference_doctype: Reference doctype filter (e.g., "CRM Lead", "CRM Task")
		reference_name: Reference document name filter (text search)
		reference_owner: Reference owner filter (text search)
		subject: Subject text search (partial match)
		content: Content text search (partial match)
		published: Published filter (0 or 1)
		seen: Seen filter (0 or 1)
		delayed: Delayed filter (0 or 1)
		ip_address: IP address filter (text search)
		creation_from: Creation date filter from (YYYY-MM-DD or DD-MM-YYYY)
		creation_to: Creation date filter to (YYYY-MM-DD or DD-MM-YYYY)
		modified_from: Modified date filter from (YYYY-MM-DD or DD-MM-YYYY)
		modified_to: Modified date filter to (YYYY-MM-DD or DD-MM-YYYY)
	
	Returns:
		{
			"message": {
				"data": [comments...],
				"page": current_page,
				"page_size": limit,
				"total": total_comments,
				"total_pages": total_pages,
				"has_next": boolean,
				"has_previous": boolean
			}
		}
	"""
	# Get parameters from form_dict for GET requests
	if hasattr(frappe, 'form_dict') and frappe.form_dict:
		# Override with form_dict values (query string takes precedence)
		comment_type = frappe.form_dict.get('comment_type') if 'comment_type' in frappe.form_dict else comment_type
		comment_email = frappe.form_dict.get('comment_email') if 'comment_email' in frappe.form_dict else comment_email
		comment_by = frappe.form_dict.get('comment_by') if 'comment_by' in frappe.form_dict else comment_by
		reference_doctype = frappe.form_dict.get('reference_doctype') if 'reference_doctype' in frappe.form_dict else reference_doctype
		reference_name = frappe.form_dict.get('reference_name') if 'reference_name' in frappe.form_dict else reference_name
		reference_owner = frappe.form_dict.get('reference_owner') if 'reference_owner' in frappe.form_dict else reference_owner
		subject = frappe.form_dict.get('subject') if 'subject' in frappe.form_dict else subject
		content = frappe.form_dict.get('content') if 'content' in frappe.form_dict else content
		published = frappe.form_dict.get('published') if 'published' in frappe.form_dict else published
		seen = frappe.form_dict.get('seen') if 'seen' in frappe.form_dict else seen
		delayed = frappe.form_dict.get('delayed') if 'delayed' in frappe.form_dict else delayed
		ip_address = frappe.form_dict.get('ip_address') if 'ip_address' in frappe.form_dict else ip_address
		creation_from = frappe.form_dict.get('creation_from') if 'creation_from' in frappe.form_dict else creation_from
		creation_to = frappe.form_dict.get('creation_to') if 'creation_to' in frappe.form_dict else creation_to
		modified_from = frappe.form_dict.get('modified_from') if 'modified_from' in frappe.form_dict else modified_from
		modified_to = frappe.form_dict.get('modified_to') if 'modified_to' in frappe.form_dict else modified_to
		page = frappe.form_dict.get('page') if 'page' in frappe.form_dict else page
		# Check form_dict first for limit, if not found use function parameter
		if 'limit' in frappe.form_dict:
			limit = frappe.form_dict.get('limit')
		order_by = frappe.form_dict.get('order_by') if 'order_by' in frappe.form_dict else order_by
	
	page = cint(page) or 1
	# If limit is 0, None, or not provided, get all comments (no pagination)
	get_all = False
	if limit is None or limit == 0 or limit == '' or limit == '0':
		get_all = True
		limit = None  # No limit
	else:
		limit = cint(limit)
		if limit < 1:
			limit = 20
		if limit > 10000:  # Very high limit means get all
			get_all = True
			limit = None
	
	if page < 1:
		page = 1
	
	# Calculate offset (only if pagination is enabled)
	if get_all:
		start = 0
		limit_page_length = None  # No limit
	else:
		start = (page - 1) * limit
		limit_page_length = limit
	
	# Build filters dynamically
	filters = []
	
	# Comment Type filter
	if comment_type and str(comment_type).strip():
		types = [t.strip() for t in comment_type.split(",") if t.strip()]
		if types:
			if len(types) == 1:
				filters.append(["comment_type", "=", types[0]])
			else:
				filters.append(["comment_type", "in", types])
	
	# Text search filters (partial match)
	if comment_email and str(comment_email).strip():
		filters.append(["comment_email", "like", f"%{comment_email}%"])
	if comment_by and str(comment_by).strip():
		filters.append(["comment_by", "like", f"%{comment_by}%"])
	if reference_name and str(reference_name).strip():
		filters.append(["reference_name", "like", f"%{reference_name}%"])
	if reference_owner and str(reference_owner).strip():
		filters.append(["reference_owner", "like", f"%{reference_owner}%"])
	if subject and str(subject).strip():
		filters.append(["subject", "like", f"%{subject}%"])
	if content and str(content).strip():
		filters.append(["content", "like", f"%{content}%"])
	if ip_address and str(ip_address).strip():
		filters.append(["ip_address", "like", f"%{ip_address}%"])
	
	# Link field filters
	if reference_doctype and str(reference_doctype).strip():
		filters.append(["reference_doctype", "=", reference_doctype])
	
	# Check field filters
	if published is not None:
		published_val = cint(published)
		filters.append(["published", "=", published_val])
	if seen is not None:
		seen_val = cint(seen)
		filters.append(["seen", "=", seen_val])
	if delayed is not None:
		delayed_val = cint(delayed)
		filters.append(["delayed", "=", delayed_val])
	
	# Helper function to normalize date format (DD-MM-YYYY to YYYY-MM-DD)
	def normalize_date(date_str):
		if not date_str:
			return None
		date_str = str(date_str).strip()
		if "-" in date_str:
			parts = date_str.split("-")
			if len(parts) == 3:
				try:
					part1 = int(parts[0])
					part2 = int(parts[1])
					part3 = int(parts[2])
					
					if part1 > 31:
						return date_str
					elif part1 <= 31 and part2 > 12:
						return f"{part3}-{part2:02d}-{part1:02d}"
					elif part1 > 12 and part2 <= 12:
						return f"{part3}-{part2:02d}-{part1:02d}"
					else:
						return date_str
				except ValueError:
					return date_str
		return date_str
	
	# Creation date filters
	if creation_from:
		creation_from = normalize_date(creation_from)
		if creation_from:
			if len(creation_from) == 10:
				filters.append(["creation", ">=", f"{creation_from} 00:00:00"])
			else:
				filters.append(["creation", ">=", creation_from])
	if creation_to:
		creation_to = normalize_date(creation_to)
		if creation_to:
			if len(creation_to) == 10:
				filters.append(["creation", "<=", f"{creation_to} 23:59:59"])
			else:
				filters.append(["creation", "<=", creation_to])
	
	# Modified date filters
	if modified_from:
		modified_from = normalize_date(modified_from)
		if modified_from:
			if len(modified_from) == 10:
				filters.append(["modified", ">=", f"{modified_from} 00:00:00"])
			else:
				filters.append(["modified", ">=", modified_from])
	if modified_to:
		modified_to = normalize_date(modified_to)
		if modified_to:
			if len(modified_to) == 10:
				filters.append(["modified", "<=", f"{modified_to} 23:59:59"])
			else:
				filters.append(["modified", "<=", modified_to])
	
	# Get total count with filters
	total = frappe.db.count("Comment", filters=filters if filters else None)
	
	# Get safe fields for Comment
	base_fields = ["name", "comment_type", "comment_email", "comment_by",
	               "reference_doctype", "reference_name", "reference_owner",
	               "subject", "content", "published", "seen", "delayed",
	               "ip_address", "creation", "modified", "owner", "modified_by"]
	fields = _safe_fields("Comment", base_fields)
	
	# Get comments with or without pagination
	if get_all:
		# Get all comments (no pagination)
		comments = frappe.get_all(
			"Comment",
			filters=filters if filters else None,
			fields=fields,
			order_by=order_by
		)
	else:
		# Get comments with pagination
		comments = frappe.get_all(
			"Comment",
			filters=filters if filters else None,
			fields=fields,
			order_by=order_by,
			limit_start=start,
			limit_page_length=limit_page_length
		)
	
	# Format comments - return all fields as-is (no special formatting needed)
	data = []
	for comment in comments:
		# Clean HTML from content if needed
		comment_dict = dict(comment)
		if 'content' in comment_dict and comment_dict['content']:
			# Keep HTML content as-is, or strip if needed
			# comment_dict['content'] = strip_html(comment_dict['content']).strip()
			pass
		data.append(comment_dict)
	
	# Calculate pagination info
	if get_all:
		# No pagination - return all data
		return {
			"message": {
				"data": data,
				"total": total,
				"page": None,
				"page_size": None,
				"total_pages": 1,
				"has_next": False,
				"has_previous": False
			}
		}
	else:
		# With pagination
		total_pages = (total + limit - 1) // limit if total > 0 else 0
		has_next = (start + len(data)) < total
		has_previous = page > 1
		
		return {
			"message": {
				"data": data,
				"page": page,
				"page_size": limit,
				"total": total,
				"total_pages": total_pages,
				"has_next": has_next,
				"has_previous": has_previous
			}
		}


@frappe.whitelist()
def home_leads(limit=5):
	"""
	Get today's top leads for home screen.
	Returns leads where assigned_date is today.
	Returns all available fields for each lead.
	
	Permission logic:
	- Each user sees only their own leads (owner = current_user)
	- Team Leader sees their own leads + leads assigned to their team members
	
	Args:
		limit: Maximum number of leads to return (default: 5)
	
	Returns:
		{"today": [leads...], "limit": N}
	"""
	today_date = today()
	current_user = frappe.session.user
	
	# Build filters for assigned_date = today
	filters = [
		["assigned_date", "=", today_date]
	]
	
	# Apply user-based permission filtering
	# Each user should only see leads they own, assigned to them, or assigned to their team
	if current_user and current_user != "Guest":
		user_roles = set(frappe.get_roles(current_user))
		
		# System Manager can see all leads (no additional filtering)
		if "System Manager" not in user_roles:
			# Build permission filters: owner OR assigned_to OR assigned_to_team
			
			# 2. Assigned to current user (via ToDo)
			# Get all leads assigned to current user
			assigned_leads = frappe.get_all(
				"ToDo",
				filters=[
					["reference_type", "=", "CRM Lead"],
					["allocated_to", "=", current_user],
					["status", "=", "Open"]
				],
				fields=["reference_name"],
				pluck="reference_name"
			)
			
			# 3. Assigned to team members (if user is Team Leader)
			# Get team members - find Team where current user is team_leader
			teams = frappe.get_all(
				"Team",
				filters={"team_leader": current_user},
				fields=["name"],
				limit=1
			)
			
			team_members = []
			if teams:
				team_name = teams[0].name
				# Get team members from Member child table
				members = frappe.get_all(
					"Member",
					filters={
						"parent": team_name,
						"parenttype": "Team"
					},
					fields=["member"],
					pluck="member"
				)
				# Filter out None/empty values
				team_members = [m for m in members if m]
			
			# Get leads assigned to team members
			team_assigned_leads = []
			if team_members:
				team_assigned_leads = frappe.get_all(
					"ToDo",
					filters=[
						["reference_type", "=", "CRM Lead"],
						["allocated_to", "in", team_members],
						["status", "=", "Open"]
					],
					fields=["reference_name"],
					pluck="reference_name"
				)
			
			# Combine all allowed lead names (assigned + team)
			allowed_lead_names = set(assigned_leads + team_assigned_leads)
			
			# Build permission filter: owner = current_user OR name in allowed_leads
			# We'll use a more efficient approach by getting owned leads and combining
			if allowed_lead_names:
				# Get owned leads and combine with assigned/team leads
				owned_leads = frappe.get_all(
					"CRM Lead",
					filters=[["owner", "=", current_user]],
					fields=["name"],
					pluck="name"
				)
				# Combine all allowed lead names
				allowed_lead_names.update(owned_leads)
				
				# Add filter to only include allowed leads
				# This efficiently combines owner + assigned + team in one filter
				filters.append(["name", "in", list(allowed_lead_names)])
			else:
				# No assigned/team leads, only show owned leads
				filters.append(["owner", "=", current_user])
	
	# Get leads with assigned_date = today and permission filters
	leads = frappe.get_all(
		"CRM Lead",
		filters=filters,
		fields=["name"],
		order_by="modified desc",
		page_length=cint(limit) or 5
	)
	
	# Get full lead documents with all fields
	data = []
	lead_names_list = [lead.name for lead in leads][:cint(limit) or 5]
	
	for lead_name in lead_names_list:
		try:
			lead_doc = frappe.get_doc("CRM Lead", lead_name)
			lead_data = get_compact_lead(lead_doc, return_all_fields=True)
			data.append(lead_data)
		except Exception as e:
			# Skip leads that can't be loaded (permissions, deleted, etc.)
			frappe.log_error(f"Error loading lead {lead_name}: {str(e)}", "home_leads_error")
			continue
	
	# Get all comments and last comment for each lead
	if data:
		try:
			lead_names = [lead.get("name") for lead in data if lead.get("name")]
			if lead_names:
				# Get all comments for each lead (with all available fields)
				all_comments = frappe.get_all(
					"Comment",
					filters=[
						["reference_doctype", "=", "CRM Lead"],
						["reference_name", "in", lead_names],
						["comment_type", "=", "Comment"]
					],
					fields=["name", "reference_name", "reference_doctype", "reference_owner",
					        "comment_type", "comment_email", "comment_by", "subject",
					        "content", "creation", "modified", "published", "seen",
					        "delayed", "ip_address"],
					order_by="creation desc"
				)
				
				# Create dictionaries mapping lead_name to comments
				last_comments = {}  # Last comment only
				all_comments_dict = {}  # All comments grouped by lead
				
				for comment in all_comments:
					lead_name = comment.get("reference_name")
					if lead_name:
						# Format comment data with all fields
						comment_data = {
							"name": comment.get("name"),
							"reference_name": comment.get("reference_name"),
							"reference_doctype": comment.get("reference_doctype"),
							"reference_owner": comment.get("reference_owner"),
							"comment_type": comment.get("comment_type"),
							"comment_email": comment.get("comment_email"),
							"comment_by": comment.get("comment_by"),
							"subject": comment.get("subject"),
							"content": comment.get("content"),
							"creation": comment.get("creation"),
							"modified": comment.get("modified"),
							"published": comment.get("published"),
							"seen": comment.get("seen"),
							"delayed": comment.get("delayed"),
							"ip_address": comment.get("ip_address")
						}
						
						# Store last comment (first one encountered is the most recent due to order_by)
						if lead_name not in last_comments:
							last_comments[lead_name] = comment_data
						
						# Store all comments
						if lead_name not in all_comments_dict:
							all_comments_dict[lead_name] = []
						all_comments_dict[lead_name].append(comment_data)
				
				# Add last_comment and comments to each lead in data
				for lead in data:
					lead_name = lead.get("name")
					# Always add comments fields, even if lead_name is None
					if lead_name and lead_name in last_comments:
						lead["last_comment"] = last_comments[lead_name]
					else:
						lead["last_comment"] = None
					
					if lead_name and lead_name in all_comments_dict:
						# Sort comments by creation desc (newest first)
						lead["comments"] = sorted(
							all_comments_dict[lead_name],
							key=lambda x: x.get("creation", ""),
							reverse=True
						)
					else:
						lead["comments"] = []
		except Exception as e:
			frappe.log_error(f"Error fetching comments: {str(e)}", "home_leads_comments_error")
			# If error occurs, set last_comment and comments to None/empty for all leads
			for lead in data:
				lead["last_comment"] = None
				lead["comments"] = []
	
	# Add Table fields (child tables) for each lead
	if data:
		try:
			lead_names = [lead.get("name") for lead in data if lead.get("name")]
			if lead_names:
				# Get duplicate_leads table data
				duplicate_leads_data = frappe.get_all(
					"Duplicate Lead Entry",
					filters=[["parent", "in", lead_names]],
					fields=["parent", "name", "lead", "lead_name", "email", "mobile_no"],
					order_by="parent, idx"
				)
				duplicate_leads_dict = {}
				for row in duplicate_leads_data:
					parent = row.get("parent")
					if parent not in duplicate_leads_dict:
						duplicate_leads_dict[parent] = []
					duplicate_leads_dict[parent].append({
						"name": row.get("name"),
						"lead": row.get("lead"),
						"lead_name": row.get("lead_name"),
						"email": row.get("email"),
						"mobile_no": row.get("mobile_no")
					})
				
				# Get status_change_log table data
				status_change_log_data = frappe.get_all(
					"CRM Status Change Log",
					filters=[["parent", "in", lead_names]],
					fields=["parent", "name", "from_status", "to_status", "changed_by", "changed_on", "reason"],
					order_by="parent, idx"
				)
				status_change_log_dict = {}
				for row in status_change_log_data:
					parent = row.get("parent")
					if parent not in status_change_log_dict:
						status_change_log_dict[parent] = []
					status_change_log_dict[parent].append({
						"name": row.get("name"),
						"from_status": row.get("from_status"),
						"to_status": row.get("to_status"),
						"changed_by": row.get("changed_by"),
						"changed_on": row.get("changed_on"),
						"reason": row.get("reason")
					})
				
				# Get property_preference_details table data
				property_preference_data = frappe.get_all(
					"Property Preference",
					filters=[["parent", "in", lead_names]],
					fields=["parent", "name", "*"],
					order_by="parent, idx"
				)
				property_preference_dict = {}
				for row in property_preference_data:
					parent = row.get("parent")
					if parent not in property_preference_dict:
						property_preference_dict[parent] = []
					# Remove parent and doctype from row data
					row_data = {k: v for k, v in row.items() if k not in ["parent", "doctype"]}
					property_preference_dict[parent].append(row_data)
				
				# Get products table data
				products_data = frappe.get_all(
					"CRM Products",
					filters=[["parent", "in", lead_names]],
					fields=["parent", "name", "*"],
					order_by="parent, idx"
				)
				products_dict = {}
				for row in products_data:
					parent = row.get("parent")
					if parent not in products_dict:
						products_dict[parent] = []
					# Remove parent and doctype from row data
					row_data = {k: v for k, v in row.items() if k not in ["parent", "doctype"]}
					products_dict[parent].append(row_data)
				
				# Add table fields to each lead
				for lead in data:
					lead_name = lead.get("name")
					if lead_name:  # Only process if lead_name is not None
						lead["duplicate_leads"] = duplicate_leads_dict.get(lead_name, [])
						lead["status_change_log"] = status_change_log_dict.get(lead_name, [])
						lead["property_preference_details"] = property_preference_dict.get(lead_name, [])
						lead["products"] = products_dict.get(lead_name, [])
					else:
						# If lead_name is None, set empty arrays
						lead["duplicate_leads"] = []
						lead["status_change_log"] = []
						lead["property_preference_details"] = []
						lead["products"] = []
		except Exception as e:
			frappe.log_error(f"Error fetching table fields: {str(e)}", "home_leads_table_fields_error")
			# If error occurs, set table fields to empty arrays for all leads
			for lead in data:
				lead["duplicate_leads"] = []
				lead["status_change_log"] = []
			lead["property_preference_details"] = []
			lead["products"] = []
	
	return {
		"today": data,
		"limit": cint(limit) or 5
	}


@frappe.whitelist(allow_guest=True)
def get_app_logo():
	"""
	Get the app logo from Website Settings.
	Returns the logo URL/path from the App Logo field.
	
	Returns:
		{
			"app_logo": "/files/logo.png" or full URL,
			"app_name": "Jossoor CRM" (optional)
		}
	"""
	try:
		# Get Website Settings document
		website_settings = frappe.get_doc("Website Settings", "Website Settings")
		
		# Get app_logo field value
		app_logo = getattr(website_settings, "app_logo", None)
		app_name = getattr(website_settings, "app_name", None)
		
		# Build full URL if app_logo exists
		logo_url = None
		if app_logo:
			# If it already starts with /, use it as is
			if app_logo.startswith("/"):
				logo_url = app_logo
			else:
				# Otherwise, prepend /files/
				logo_url = f"/files/{app_logo}"
			
			# Optionally build full URL with site URL
			# Uncomment the following lines if you want full URL instead of relative path
			# from frappe.utils import get_url
			# site_url = get_url()
			# logo_url = f"{site_url}{logo_url}"
		
		return {
			"app_logo": logo_url,
			"app_name": app_name
		}
	except Exception as e:
		frappe.log_error(f"Error getting app logo: {str(e)}", "get_app_logo_error")
		return {
			"app_logo": None,
			"app_name": None,
			"error": str(e)
		}


@frappe.whitelist()
def get_lead_by_id(lead_id=None, name=None):
	"""
	Get a single CRM Lead by ID with all fields, comments, and table data.
	
	Args:
		lead_id: Lead ID (name) - required (can also use 'name')
		name: Lead name (alias for lead_id)
	
	Returns:
		{
			"lead": {
				...all lead fields...,
				"last_comment": {...},
				"comments": [...],
				"duplicate_leads": [...],
				"status_change_log": [...],
				"property_preference_details": [...],
				"products": [...]
			}
		}
	"""
	# Resolve lead_id/name parameter
	lead_name = lead_id or name
	if not lead_name:
		return {
			"error": "lead_id or name parameter is required"
		}
	
	try:
		# Get all fields from CRM Lead doctype (same approach as get_all_leads)
		# This ensures all fields including custom fields are returned
		meta = frappe.get_meta("CRM Lead")
		all_fieldnames = [f.fieldname for f in meta.fields 
		                  if f.fieldtype not in ['Tab Break', 'Section Break', 'Column Break', 'Table']]
		
		# Ensure 'name' field is always included (it's a system field)
		if 'name' not in all_fieldnames:
			all_fieldnames.insert(0, 'name')
		
		# Use _safe_fields to filter out any problematic fields
		fields = _safe_fields("CRM Lead", all_fieldnames)
		
		# Get lead with all fields using frappe.get_all (same as get_all_leads)
		leads = frappe.get_all(
			"CRM Lead",
			filters={"name": lead_name},
			fields=fields,
			limit=1
		)
		
		if not leads:
			return {
				"error": f"Lead with ID '{lead_name}' not found"
			}
		
		# Get lead document for get_compact_lead
		lead_doc = frappe.get_doc("CRM Lead", lead_name)
		
		# Get all fields using get_compact_lead
		lead_data = get_compact_lead(lead_doc, return_all_fields=True)
		
		# Ensure all fields from frappe.get_all are included (especially assigned_to_display)
		# Merge fields from frappe.get_all to ensure we have all fields including computed ones
		for fieldname in fields:
			if fieldname in leads[0]:
				# Only override if the field exists in the get_all result
				# This ensures computed fields like assigned_to_display are included
				if fieldname not in lead_data or lead_data.get(fieldname) is None:
					lead_data[fieldname] = leads[0].get(fieldname)
		
		# Ensure name is always present
		if not lead_data.get("name"):
			lead_data["name"] = lead_name
		
		# Get all comments and last comment
		try:
			# Get all comments for this lead
			all_comments = frappe.get_all(
				"Comment",
				filters=[
					["reference_doctype", "=", "CRM Lead"],
					["reference_name", "=", lead_name],
					["comment_type", "=", "Comment"]
				],
				fields=["name", "reference_name", "reference_doctype", "reference_owner",
				        "comment_type", "comment_email", "comment_by", "subject",
				        "content", "creation", "modified", "published", "seen",
				        "delayed", "ip_address"],
				order_by="creation desc"
			)
			
			# Format comments
			comments_list = []
			last_comment = None
			
			for comment in all_comments:
				comment_data = {
					"name": comment.get("name"),
					"reference_name": comment.get("reference_name"),
					"reference_doctype": comment.get("reference_doctype"),
					"reference_owner": comment.get("reference_owner"),
					"comment_type": comment.get("comment_type"),
					"comment_email": comment.get("comment_email"),
					"comment_by": comment.get("comment_by"),
					"subject": comment.get("subject"),
					"content": comment.get("content"),
					"creation": comment.get("creation"),
					"modified": comment.get("modified"),
					"published": comment.get("published"),
					"seen": comment.get("seen"),
					"delayed": comment.get("delayed"),
					"ip_address": comment.get("ip_address")
				}
				
				comments_list.append(comment_data)
				
				# First comment is the most recent (due to order_by)
				if last_comment is None:
					last_comment = comment_data
			
			# Sort comments by creation desc (newest first)
			comments_list = sorted(
				comments_list,
				key=lambda x: x.get("creation", ""),
				reverse=True
			)
			
			lead_data["last_comment"] = last_comment
			lead_data["comments"] = comments_list
		except Exception as e:
			frappe.log_error(f"Error fetching comments for lead {lead_name}: {str(e)}", "get_lead_by_id_comments_error")
			lead_data["last_comment"] = None
			lead_data["comments"] = []
		
		# Get Table fields (child tables)
		try:
			# Get duplicate_leads table data
			duplicate_leads_data = frappe.get_all(
				"Duplicate Lead Entry",
				filters=[["parent", "=", lead_name]],
				fields=["parent", "name", "lead", "lead_name", "email", "mobile_no"],
				order_by="idx"
			)
			duplicate_leads_list = []
			for row in duplicate_leads_data:
				duplicate_leads_list.append({
					"name": row.get("name"),
					"lead": row.get("lead"),
					"lead_name": row.get("lead_name"),
					"email": row.get("email"),
					"mobile_no": row.get("mobile_no")
				})
			lead_data["duplicate_leads"] = duplicate_leads_list
			
			# Get status_change_log table data
			status_change_log_data = frappe.get_all(
				"CRM Status Change Log",
				filters=[["parent", "=", lead_name]],
				fields=["parent", "name", "from_status", "to_status", "changed_by", "changed_on", "reason"],
				order_by="idx"
			)
			status_change_log_list = []
			for row in status_change_log_data:
				status_change_log_list.append({
					"name": row.get("name"),
					"from_status": row.get("from_status"),
					"to_status": row.get("to_status"),
					"changed_by": row.get("changed_by"),
					"changed_on": row.get("changed_on"),
					"reason": row.get("reason")
				})
			lead_data["status_change_log"] = status_change_log_list
			
			# Get property_preference_details table data
			property_preference_data = frappe.get_all(
				"Property Preference",
				filters=[["parent", "=", lead_name]],
				fields=["parent", "name", "*"],
				order_by="idx"
			)
			property_preference_list = []
			for row in property_preference_data:
				# Remove parent and doctype from row data
				row_data = {k: v for k, v in row.items() if k not in ["parent", "doctype"]}
				property_preference_list.append(row_data)
			lead_data["property_preference_details"] = property_preference_list
			
			# Get products table data
			products_data = frappe.get_all(
				"CRM Products",
				filters=[["parent", "=", lead_name]],
				fields=["parent", "name", "*"],
				order_by="idx"
			)
			products_list = []
			for row in products_data:
				# Remove parent and doctype from row data
				row_data = {k: v for k, v in row.items() if k not in ["parent", "doctype"]}
				products_list.append(row_data)
			lead_data["products"] = products_list
		except Exception as e:
			frappe.log_error(f"Error fetching table fields for lead {lead_name}: {str(e)}", "get_lead_by_id_table_fields_error")
			lead_data["duplicate_leads"] = []
			lead_data["status_change_log"] = []
			lead_data["property_preference_details"] = []
			lead_data["products"] = []
		
		return {
			"lead": lead_data
		}
	except frappe.DoesNotExistError:
		return {
			"error": f"Lead with ID '{lead_name}' not found"
		}
	except Exception as e:
		frappe.log_error(f"Error getting lead {lead_name}: {str(e)}", "get_lead_by_id_error")
		return {
			"error": str(e)
		}



#--------------------------------------------------------------------------------------------------


@frappe.whitelist()
def create_task_with_reminder(
    title=None,
    description=None,
    assigned_to=None,
    due_date=None,
    reminder_at=None,
    status="Backlog",
    priority="Low",
    reference_doctype=None,
    reference_docname=None,
    task_type=None,
    meeting_attendees=None,
    start_date=None,
    assigned_to_list=None,
    **kwargs
):
    """
    Create CRM Task with optional reminder in a single API call.
    Designed for mobile app compatibility.
    
    Args:
        title: Task title
        description: Task description
        assigned_to: Single user email (legacy support)
        due_date: Task due date
        reminder_at: Reminder datetime (YYYY-MM-DD HH:MM:SS) ⭐ NEW
        status: Task status (default: "Backlog")
        priority: Task priority (default: "Low")
        reference_doctype: Reference document type
        reference_docname: Reference document name
        task_type: Task type (required)
        meeting_attendees: List of user objects for meetings
        start_date: Task start date
        assigned_to_list: List of user emails to assign
        **kwargs: Any other CRM Task fields
    
    Returns:
        Full task JSON with all fields
    """
    # Use existing create_task function to create the task
    task_result = create_task(
        title=title,
        description=description,
        assigned_to=assigned_to,
        due_date=due_date,
        status=status,
        priority=priority,
        reference_doctype=reference_doctype,
        reference_docname=reference_docname,
        task_type=task_type,
        meeting_attendees=meeting_attendees,
        start_date=start_date,
        assigned_to_list=assigned_to_list,
        **kwargs
    )
    
    # Get task name from result
    task_name = task_result.get("name")
    
    # Create reminder if provided
    if reminder_at and task_name:
        try:
            # Get assigned user (use assigned_to or first user from assigned_to_list)
            reminder_user = assigned_to
            if not reminder_user and assigned_to_list:
                if isinstance(assigned_to_list, str):
                    try:
                        assigned_to_list = frappe.parse_json(assigned_to_list)
                    except:
                        assigned_to_list = [assigned_to_list]
                
                if isinstance(assigned_to_list, list) and len(assigned_to_list) > 0:
                    user_data = assigned_to_list[0]
                    if isinstance(user_data, dict):
                        reminder_user = user_data.get("email") or user_data.get("id")
                    elif isinstance(user_data, str):
                        reminder_user = user_data
            
            # Default to current user if no assigned user
            if not reminder_user:
                reminder_user = frappe.session.user
            
            # Create reminder document
            reminder_doc = frappe.get_doc({
                "doctype": "Reminder",
                "user": reminder_user,
                "remind_at": reminder_at,
                "description": title or description or "",
                "reference_doctype": "CRM Task",
                "reference_docname": task_name,
            })
            reminder_doc.insert(ignore_permissions=True)
            frappe.db.commit()
            
            # Add reminder_at to task result
            task_result["reminder_at"] = reminder_at
        except Exception as e:
            frappe.log_error(f"Error creating reminder for task {task_name}: {str(e)}", "Task Reminder Creation Error")
            # Don't fail the task creation, just log the error
            task_result["reminder_error"] = str(e)
    
    return task_result


@frappe.whitelist()
def update_task_with_reminder(
    task_id=None,
    name=None,
    title=None,
    description=None,
    assigned_to=None,
    due_date=None,
    reminder_at=None,
    status=None,
    priority=None,
    task_type=None,
    meeting_attendees=None,
    start_date=None,
    assigned_to_list=None,
    reference_doctype=None,
    reference_docname=None,
    **kwargs
):
    """
    Update CRM Task and handle reminder in a single API call.
    Designed for mobile app compatibility.
    
    Args:
        task_id: Task ID (name) - required
        name: Task name (alias for task_id)
        reminder_at: Reminder datetime or null to remove ⭐ NEW
        ... (other fields same as edit_task)
    
    Returns:
        Updated task JSON with all fields including reminder_at
    """
    # Get task name
    task_name = task_id or name
    if not task_name:
        frappe.throw(_("Task ID is required"))
    
    # Use existing edit_task function to update the task
    task_result = edit_task(
        task_id=task_name,
        title=title,
        description=description,
        assigned_to=assigned_to,
        due_date=due_date,
        status=status,
        priority=priority,
        task_type=task_type,
        meeting_attendees=meeting_attendees,
        start_date=start_date,
        assigned_to_list=assigned_to_list,
        reference_doctype=reference_doctype,
        reference_docname=reference_docname,
        **kwargs
    )
    
    # Handle reminder (create, update, or delete)
    try:
        # Get existing reminder
        existing_reminders = frappe.get_all(
            "Reminder",
            filters={
                "reference_doctype": "CRM Task",
                "reference_docname": task_name
            },
            fields=["name", "remind_at"],
            limit=1
        )
        
        if reminder_at:
            # Get assigned user for reminder
            task_doc = frappe.get_doc("CRM Task", task_name)
            reminder_user = task_doc.assigned_to or frappe.session.user
            
            if existing_reminders:
                # Update existing reminder
                reminder_doc = frappe.get_doc("Reminder", existing_reminders[0].name)
                reminder_doc.remind_at = reminder_at
                reminder_doc.user = reminder_user
                reminder_doc.save(ignore_permissions=True)
            else:
                # Create new reminder
                reminder_doc = frappe.get_doc({
                    "doctype": "Reminder",
                    "user": reminder_user,
                    "remind_at": reminder_at,
                    "description": task_result.get("title") or task_result.get("description") or "",
                    "reference_doctype": "CRM Task",
                    "reference_docname": task_name,
                })
                reminder_doc.insert(ignore_permissions=True)
            
            task_result["reminder_at"] = reminder_at
        else:
            # reminder_at is None/empty - delete existing reminder
            if existing_reminders:
                frappe.delete_doc("Reminder", existing_reminders[0].name, ignore_permissions=True, force=1)
            
            task_result["reminder_at"] = None
        
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"Error updating reminder for task {task_name}: {str(e)}", "Task Reminder Update Error")
        task_result["reminder_error"] = str(e)
    
    return task_result


@frappe.whitelist()
def get_task_with_reminder(task_id=None, name=None):
    """
    Get task with reminder information included.
    
    Args:
        task_id: Task ID (name) - required
        name: Task name (alias for task_id)
    
    Returns:
        {
            "task": {...all task fields..., "reminder_at": "2025-01-15 09:00:00"}
        }
    """
    # Get task name
    task_name = task_id or name
    if not task_name:
        frappe.throw(_("Task ID is required"))
    
    try:
        # Get task document
        task_doc = frappe.get_doc("CRM Task", task_name)
        task_dict = get_compact_task(task_doc, return_all_fields=True)
        
        # Fetch reminder if exists
        reminder = frappe.get_all(
            "Reminder",
            filters={
                "reference_doctype": "CRM Task",
                "reference_docname": task_name
            },
            fields=["name", "remind_at"],
            limit=1
        )
        
        task_dict["reminder_at"] = reminder[0].remind_at if reminder else None
        
        return task_dict
    except frappe.DoesNotExistError:
        frappe.throw(_("Task {0} not found").format(task_name))
    except Exception as e:
        frappe.log_error(f"Error fetching task with reminder: {str(e)}", "Get Task With Reminder Error")
        frappe.throw(_("Failed to fetch task: {0}").format(str(e)))


def get_compact_project(project, return_all_fields=False):
	"""
	Return project representation.
	Accepts both Document objects and dict-like objects.
	"""
	def _get(obj, key, default=None):
		if isinstance(obj, dict):
			return obj.get(key, default)
		return getattr(obj, key, default)
	
	project_name = project.name if hasattr(project, "name") else project.get("name")
	
	if return_all_fields:
		result = {}
		if isinstance(project, dict):
			for key, value in project.items():
				if key not in ['doctype'] and value is not None:
					result[key] = value
			if 'description' in result and result['description']:
				result['description'] = strip_html(result['description']).strip()
		else:
			# Document object
			for field in project.meta.fields:
				fieldname = field.fieldname
				if fieldname in ['doctype']:
					continue
				if field.fieldtype == 'Table':
					continue
				value = getattr(project, fieldname, None)
				important_fields = ['name', 'modified', 'creation', 'owner', 'modified_by', 'description']
				if value is not None or fieldname in important_fields:
					result[fieldname] = value
			
			result['name'] = project.name
			if hasattr(project, 'modified'):
				result['modified'] = project.modified
			if hasattr(project, 'creation'):
				result['creation'] = project.creation
			if hasattr(project, 'owner'):
				result['owner'] = project.owner
			if hasattr(project, 'modified_by'):
				result['modified_by'] = project.modified_by
			
			if 'description' in result and result['description']:
				result['description'] = strip_html(result['description']).strip()
	else:
		result = {
			"name": project_name,
			"project_name": _get(project, "project_name"),
			"status": _get(project, "status"),
			"developer": _get(project, "developer"),
			"location": _get(project, "location"),
			"min_price": _get(project, "min_price"),
			"max_price": _get(project, "max_price"),
			"cover_image": _get(project, "cover_image"),
			"city": _get(project, "city"),
			"district": _get(project, "district")
		}
	
	return result


@frappe.whitelist()
def get_all_projects(page=1, limit=20, order_by="modified desc",
					 status=None, developer=None, location=None,
					 min_price_from=None, min_price_to=None,
					 max_price_from=None, max_price_to=None,
					 project_name=None, city=None, district=None,
					 categories=None, exclusivity=None, furnishing=None,
					 **kwargs):
	"""
	Get all Real Estate Projects with pagination and filtering.
	"""
	if hasattr(frappe, 'form_dict') and frappe.form_dict:
		status = frappe.form_dict.get('status') if 'status' in frappe.form_dict else status
		developer = frappe.form_dict.get('developer') if 'developer' in frappe.form_dict else developer
		location = frappe.form_dict.get('location') if 'location' in frappe.form_dict else location
		min_price_from = frappe.form_dict.get('min_price_from') if 'min_price_from' in frappe.form_dict else min_price_from
		min_price_to = frappe.form_dict.get('min_price_to') if 'min_price_to' in frappe.form_dict else min_price_to
		max_price_from = frappe.form_dict.get('max_price_from') if 'max_price_from' in frappe.form_dict else max_price_from
		max_price_to = frappe.form_dict.get('max_price_to') if 'max_price_to' in frappe.form_dict else max_price_to
		project_name = frappe.form_dict.get('project_name') if 'project_name' in frappe.form_dict else project_name
		city = frappe.form_dict.get('city') if 'city' in frappe.form_dict else city
		district = frappe.form_dict.get('district') if 'district' in frappe.form_dict else district
		categories = frappe.form_dict.get('categories') if 'categories' in frappe.form_dict else categories
		exclusivity = frappe.form_dict.get('exclusivity') if 'exclusivity' in frappe.form_dict else exclusivity
		furnishing = frappe.form_dict.get('furnishing') if 'furnishing' in frappe.form_dict else furnishing
		page = frappe.form_dict.get('page') if 'page' in frappe.form_dict else page
		limit = frappe.form_dict.get('limit') if 'limit' in frappe.form_dict else limit
		order_by = frappe.form_dict.get('order_by') if 'order_by' in frappe.form_dict else order_by

	page = cint(page) or 1
	limit = cint(limit) or 20
	if page < 1: page = 1
	if limit < 1: limit = 20
	if limit > 100: limit = 100
	
	start = (page - 1) * limit
	
	filters = []
	
	if status and str(status).strip():
		statuses = [s.strip() for s in status.split(",") if s.strip()]
		if statuses:
			if len(statuses) == 1:
				filters.append(["status", "=", statuses[0]])
			else:
				filters.append(["status", "in", statuses])
				
	if developer and str(developer).strip():
		filters.append(["developer", "like", f"%{developer}%"])
		
	if location and str(location).strip():
		filters.append(["location", "like", f"%{location}%"])
		
	if project_name and str(project_name).strip():
		filters.append(["project_name", "like", f"%{project_name}%"])
		
	if city and str(city).strip():
		filters.append(["city", "like", f"%{city}%"])
		
	if district and str(district).strip():
		filters.append(["district", "like", f"%{district}%"])

	if categories and str(categories).strip():
		cat_list = [c.strip() for c in categories.split(",") if c.strip()]
		if cat_list:
			if len(cat_list) == 1:
				filters.append(["categories", "=", cat_list[0]])
			else:
				filters.append(["categories", "in", cat_list])
				
	if exclusivity and str(exclusivity).strip():
		filters.append(["exclusivity", "=", exclusivity])
		
	if furnishing and str(furnishing).strip():
		filters.append(["furnishing", "=", furnishing])

	if min_price_from:
		filters.append(["min_price", ">=", float(min_price_from)])
	if min_price_to:
		filters.append(["min_price", "<=", float(min_price_to)])
		
	if max_price_from:
		filters.append(["max_price", ">=", float(max_price_from)])
	if max_price_to:
		filters.append(["max_price", "<=", float(max_price_to)])

	# Get total count
	total = frappe.db.count("Real Estate Project", filters=filters if filters else None)
	
	# Get all fields
	meta = frappe.get_meta("Real Estate Project")
	all_fieldnames = [f.fieldname for f in meta.fields 
					  if f.fieldtype not in ['Tab Break', 'Section Break', 'Column Break', 'Table']]
	if 'name' not in all_fieldnames:
		all_fieldnames.insert(0, 'name')
		
	fields = _safe_fields("Real Estate Project", all_fieldnames)
	
	projects = frappe.get_all(
		"Real Estate Project",
		filters=filters if filters else None,
		fields=fields,
		order_by=order_by,
		limit_start=start,
		limit_page_length=limit
	)
	
	data = [get_compact_project(p, return_all_fields=True) for p in projects]
	
	total_pages = (total + limit - 1) // limit if total > 0 else 0
	has_next = (start + len(data)) < total
	has_previous = page > 1
	
	return {
		"message": {
			"data": data,
			"page": page,
			"page_size": limit,
			"total": total,
			"total_pages": total_pages,
			"has_next": has_next,
			"has_previous": has_previous
		}
	}


@frappe.whitelist()
def get_project_by_id(project_id=None, name=None):
	"""
	Get a single Real Estate Project by ID (or project_name).
	"""
	pid = project_id or name
	if not pid:
		frappe.throw(_("Project ID is required"))
		
	if not frappe.db.exists("Real Estate Project", pid):
		frappe.throw(_("Project not found"))
		
	doc = frappe.get_doc("Real Estate Project", pid)
	project_dict = get_compact_project(doc, return_all_fields=True)
	
	# Add child tables
	if hasattr(doc, 'gallery'):
		project_dict['gallery'] = []
		for item in doc.gallery:
			project_dict['gallery'].append({
				'image': item.image,
				'description': item.description
			})
			
	return {
		"message": project_dict
	}


@frappe.whitelist()
def create_project(**kwargs):
	"""
	Create a new Real Estate Project.
	"""
	try:
		doc = frappe.new_doc("Real Estate Project")
		doc.update(kwargs)
		doc.insert()
		return get_compact_project(doc, return_all_fields=True)
	except Exception as e:
		frappe.log_error(f"Error creating project: {str(e)}", "Create Project Error")
		frappe.throw(_("Failed to create project: {0}").format(str(e)))


@frappe.whitelist()
def update_project(project_id, **kwargs):
	"""
	Update an existing Real Estate Project.
	"""
	if not project_id:
		frappe.throw(_("Project ID is required"))
	
	try:
		doc = frappe.get_doc("Real Estate Project", project_id)
		doc.update(kwargs)
		doc.save()
		return get_compact_project(doc, return_all_fields=True)
	except Exception as e:
		frappe.log_error(f"Error updating project: {str(e)}", "Update Project Error")
		frappe.throw(_("Failed to update project: {0}").format(str(e)))


@frappe.whitelist()
def delete_project(project_id):
	"""
	Delete a Real Estate Project.
	"""
	if not project_id:
		frappe.throw(_("Project ID is required"))
		
	try:
		frappe.delete_doc("Real Estate Project", project_id)
		return {"status": "success", "message": _("Project deleted successfully")}
	except Exception as e:
		frappe.log_error(f"Error deleting project: {str(e)}", "Delete Project Error")
		frappe.throw(_("Failed to delete project: {0}").format(str(e)))