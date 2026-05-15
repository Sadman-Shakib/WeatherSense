from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/api/sensor', methods=['POST'])
def receive_json():
    try:
        data = request.get_json()  # Get JSON data from request
        
        if data is None:
            return jsonify({"error": "No JSON received"}), 400

        # Print JSON nicely in console
        print("Received JSON Data:")
        print(data)

        return jsonify({"message": "Data received successfully"}), 200

    except Exception as e:
        print("Error:", str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

