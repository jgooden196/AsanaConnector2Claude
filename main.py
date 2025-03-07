import os
import logging
import sys
from flask import Flask, request, jsonify
from asana import Client

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger()

# Asana API setup
asana_token = os.environ.get('ASANA_TOKEN')
client = Client.access_token(asana_token)

# Your Asana project ID
project_id = '1209353707682767'

# Constants
STATUS_TASK_NAME = "Project Status"
ESTIMATED_COST_FIELD = "Budget"  # You'll need to replace this with your actual custom field name
ACTUAL_COST_FIELD = "Actual Cost"  # You'll need to replace this with your actual custom field name

# Dictionary to store webhook secret dynamically
WEBHOOK_SECRET = {}

def get_custom_fields():
    """Get the custom field GIDs for Estimated Cost and Actual Cost fields"""
    try:
        # Get all custom field settings for the project
        custom_field_settings = client.custom_field_settings.find_by_project(project_id)
        
        estimated_cost_gid = None
        actual_cost_gid = None
        
        for setting in custom_field_settings:
            field_name = setting['custom_field']['name']
            if field_name == ESTIMATED_COST_FIELD:
                estimated_cost_gid = setting['custom_field']['gid']
            elif field_name == ACTUAL_COST_FIELD:
                actual_cost_gid = setting['custom_field']['gid']
        
        return estimated_cost_gid, actual_cost_gid
    except Exception as e:
        logger.error(f"Error getting custom fields: {e}")
        return None, None

def find_status_task():
    """Find the Project Status task in the project"""
    try:
        tasks = client.tasks.find_by_project(project_id)
        for task in tasks:
            if task['name'] == STATUS_TASK_NAME:
                return task['gid']
        return None
    except Exception as e:
        logger.error(f"Error finding status task: {e}")
        return None

def create_status_task():
    """Create the Project Status task"""
    try:
        task = client.tasks.create_in_workspace({
            'name': STATUS_TASK_NAME,
            'projects': [project_id],
            'notes': "This task contains summary information about the project budget."
        })
        logger.info(f"Created Project Status task with GID: {task['gid']}")
        return task['gid']
    except Exception as e:
        logger.error(f"Error creating status task: {e}")
        return None

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Handles incoming webhook requests from Asana"""
    # Check if this is the webhook handshake request
    if 'X-Hook-Secret' in request.headers:
        secret = request.headers['X-Hook-Secret']
        WEBHOOK_SECRET['secret'] = secret  # Store secret dynamically
        
        response = jsonify({})
        response.headers['X-Hook-Secret'] = secret  # Send back the secret
         
        logger.info(f"Webhook Handshake Successful. Secret: {secret}")
        return response, 200
    
    # If it's not a handshake, it's an event
    try:
        data = request.json
        logger.info(f"Received Asana Event: {data}")
        
        # Get custom field GIDs
        estimated_cost_gid, actual_cost_gid = get_custom_fields()
        
        # Process events
        events = data.get('events', [])
        should_update = False
        
        for event in events:
            # Check if this is a task event that could affect our metrics
            if event.get('resource', {}).get('resource_type') == 'task':
                # Always update if a task is added or removed
                action = event.get('action')
                if action in ['added', 'removed', 'deleted', 'undeleted']:
                    should_update = True
                    break
                
                # For changes, check if it involves the actual cost field
                if action == 'changed':
                    resource = event.get('resource', {})
                    # If this is a task and we know the actual cost field GID, check if it changed
                    if actual_cost_gid and resource.get('resource_type') == 'task':
                        # Update if any custom field changed (we'll filter by actual cost)
                        if 'custom_field' in event.get('parent', {}).get('resource_type', ''):
                            should_update = True
                            break
        
        if should_update or not events:  # Also handle heartbeat events (empty events list)
            # Update metrics
            update_project_metrics()
        
        return jsonify({"status": "received"}), 200
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Handles incoming webhook requests from Asana"""
    # Check if this is the webhook handshake request
    if 'X-Hook-Secret' in request.headers:
        secret = request.headers['X-Hook-Secret']
        WEBHOOK_SECRET['secret'] = secret  # Store secret dynamically
        
        # Log after preparing the response to ensure fast response time
        response = jsonify({})
        response.headers['X-Hook-Secret'] = secret  # Send back the secret
        
        # Use a background thread to log after sending the response
        import threading
        def log_success():
            logger.info(f"Webhook Handshake Successful. Secret: {secret}")
        threading.Thread(target=log_success).start()
        
        return response, 200
    
    # Rest of the function remains the same
    # ...
@app.route('/setup', methods=['GET'])
def setup():
    """Setup endpoint to initialize the project status task and metrics"""
    # Find or create status task
    status_task_gid = find_status_task()
    if not status_task_gid:
        status_task_gid = create_status_task()
    
    # Update metrics
    success = update_project_metrics()
    
    if success:
        return jsonify({
            "status": "success", 
            "message": "Project status task created and metrics updated"
        }), 200
    else:
        return jsonify({
            "status": "error", 
            "message": "Failed to setup project status"
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200
@app.route('/register-webhook', methods=['GET'])
def register_webhook():
    """Register a webhook for the project"""
    try:
        # Force HTTPS for Railway app URL
        webhook_url = "https://asanaconnector2claude-production.up.railway.app/webhook"
        
        # Register the webhook
        webhook = client.webhooks.create({
            'resource': project_id,
            'target': webhook_url
        })
        
        logger.info(f"Webhook registered: {webhook['gid']}")
        return jsonify({
            "status": "success", 
            "message": f"Webhook registered for project {project_id}", 
            "webhook_gid": webhook['gid'],
            "target_url": webhook_url
        }), 200
        
    except Exception as e:
        logger.error(f"Error registering webhook: {e}")
        return jsonify({
            "status": "error", 
            "message": f"Failed to register webhook: {str(e)}"
        }), 500
if __name__ == '__main__':
    app.run(debug=True)
