import os
import logging
import sys
from flask import Flask, request, jsonify
from asana import Client, errors

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
        # Get all custom fields for the project
        custom_fields = client.projects.get_custom_field_settings_for_project(project_id)
        
        estimated_cost_gid = None
        actual_cost_gid = None
        
        for field in custom_fields:
            field_name = field['custom_field']['name']
            if field_name == ESTIMATED_COST_FIELD:
                estimated_cost_gid = field['custom_field']['gid']
            elif field_name == ACTUAL_COST_FIELD:
                actual_cost_gid = field['custom_field']['gid']
        
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

def update_project_metrics():
    """Calculate project metrics and update the Project Status task"""
    try:
        estimated_cost_gid, actual_cost_gid = get_custom_fields()
        if not estimated_cost_gid or not actual_cost_gid:
            logger.error("Could not find custom field GIDs")
            return False
        
        # Get all tasks in the project
        tasks = client.tasks.find_by_project(project_id)
        
        total_estimated = 0
        total_actual = 0
        completed_tasks = 0
        total_tasks = 0
        overbudget_tasks = []
        
        # Find status task or create if not exists
        status_task_gid = find_status_task()
        if not status_task_gid:
            status_task_gid = create_status_task()
            if not status_task_gid:
                return False
        
        # Process each task
        for task in tasks:
            task_gid = task['gid']
            
            # Skip the status task itself
            if task_gid == status_task_gid:
                continue
            
            # Get full task details to access custom fields
            task_details = client.tasks.find_by_id(task_gid)
            
            total_tasks += 1
            
            # Extract costs from custom fields
            estimated_cost = 0
            actual_cost = 0
            
            if 'custom_fields' in task_details:
                for field in task_details['custom_fields']:
                    if field['gid'] == estimated_cost_gid and field.get('number_value') is not None:
                        estimated_cost = field['number_value']
                    elif field['gid'] == actual_cost_gid and field.get('number_value') is not None:
                        actual_cost = field['number_value']
            
            # Add to totals
            total_estimated += estimated_cost
            
            # Only add actual costs if they exist (work completed)
            if actual_cost > 0:
                total_actual += actual_cost
                completed_tasks += 1
                
                # Check if task is over budget
                if actual_cost > estimated_cost:
                    overbudget_tasks.append({
                        'name': task['name'],
                        'estimated': estimated_cost,
                        'actual': actual_cost,
                        'difference': actual_cost - estimated_cost
                    })
        
        # Create summary
        percent_complete = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        budget_progress = (total_actual / total_estimated * 100) if total_estimated > 0 else 0
        
        summary = f"""# Construction Project Budget Summary

## Overall Budget
- Total Estimated Budget: ${total_estimated:.2f}
- Total Actual Cost Incurred: ${total_actual:.2f}
- Remaining Budget: ${total_estimated - total_actual:.2f}
- Budget Utilization: {budget_progress:.1f}%

## Progress
- Total Tasks: {total_tasks}
- Completed Tasks (with actual costs): {completed_tasks}
- Project Completion: {percent_complete:.1f}%

"""
        
        # Add overbudget section if there are overbudget tasks
        if overbudget_tasks:
            summary += "## Overbudget Items\n"
            for item in overbudget_tasks:
                summary += f"- {item['name']}: Estimated ${item['estimated']:.2f}, Actual ${item['actual']:.2f} (${item['difference']:.2f} over budget)\n"
            
            total_overbudget = sum(item['difference'] for item in overbudget_tasks)
            summary += f"\nTotal Amount Over Budget: ${total_overbudget:.2f}\n"
        
        # Update the status task
        client.tasks.update(status_task_gid, {
            'notes': summary
        })
        
        logger.info("Successfully updated project metrics")
        return True
        
    except Exception as e:
        logger.error(f"Error updating project metrics: {e}")
        return False

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
        
        # Process events
        events = data.get('events', [])
        for event in events:
            # Check if this is a task event that could affect our metrics
            if event.get('resource', {}).get('resource_type') == 'task':
                # Tasks were modified, added, or completed - update our metrics
                update_project_metrics()
                break
        
        return jsonify({"status": "received"}), 200
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

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

if __name__ == '__main__':
    app.run(debug=True)
