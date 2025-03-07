import os
from flask import Flask, request, jsonify
from asana import Client

app = Flask(__name__)

# Asana API setup
asana_token = os.environ.get('ASANA_TOKEN')
client = Client.access_token(asana_token)

# Your Asana project ID
project_id = '1209353707682767'

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    event = request.json
    # We'll add more code here later
    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    app.run(debug=True)
