import os
from flask import Flask, request, jsonify
from asana import Client

app = Flask(__name__)

# Asana API setup
asana_token = os.environ.get('ASANA_TOKEN')
client = Client.access_token(asana_token)

# Your Asana project ID
project_id = 'YOUR_PROJECT_ID'

# Function to update or create the Project Status task
def update_project_status():
    # Get all tasks in the project
    tasks = list(client.tasks.get_tasks_for_project(project_id, opt_fields=['name', 'custom_fields']))
    
    # Calculate totals and gather metrics
    total_estimated = sum(float(task['custom_fields']['Estimated Cost']) for task in tasks if task['custom_fields'].get('Estimated Cost'))
    total_actual = sum(float(task['custom_fields']['Actual Cost']) for task in tasks if task['custom_fields'].get('Actual Cost'))
    overbudget_tasks = [task['name'] for task in tasks if float(task['custom_fields'].get('Actual Cost', 0)) > float(task['custom_fields'].get('Estimated Cost', 0))]
    
    # Prepare status description
    status_description = f"""
    Total Estimated Budget: ${total_estimated:.2f}
    Total Actual Cost Incurred: ${total_actual:.2f}
    Overbudget Tasks: {', '.join(overbudget_tasks) if overbudget_tasks else 'None'}
    """
    
    # Find or create the Project Status task
    status_task = next((task for task in tasks if task['name'] == 'Project Status'), None)
    if status_task:
        # Update existing task
        client.tasks.update_task(status_task['gid'], {'notes': status_description})
    else:
        # Create new task
        client.tasks.create_task({
            'name': 'Project Status',
            'projects': [project_id],
            'notes': status_description
        })

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    event = request.json
    if event['resource_type'] == 'task':
        update_project_status()
    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    app.run(debug=True)
