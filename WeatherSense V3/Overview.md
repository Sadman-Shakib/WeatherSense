# WeatherSense V3 - Project Overview & Technical Details

## 1. Project Architecture
This project is a complete IoT and Machine Learning-based weather monitoring and forecasting system. It consists of two main parts:
- **Hardware (ESP32):** Reads real-time data from sensors and sends it to the server.
- **Software (Flask Backend + ML):** Receives the data, saves it to the database, displays it on the dashboard, and uses machine learning to forecast the future weather.

---

## 2. Live Sensor Reading
**How does it work and where does the data come from?**
- Your ESP32 microcontroller reads data every 2 seconds from the DHT11 (temperature and humidity), BMP280 (air pressure), and Rain sensor.
- The ESP32 then packages this data into a JSON format and sends it via the internet (Wi-Fi) through an HTTP POST request to the `/api/sensor` endpoint of your Flask server running on your laptop.
- The Flask server receives this data and immediately saves it into the `weather.db` (SQLite) database.
- The "Live Sensor Reading" section on the dashboard fetches the most recently updated (latest) data from the database and displays it on the screen.

---

## 3. Forecast Section
**Does it predict based on the latest data or just show the trained data?**
- The forecast section is **completely dynamic and works based on the latest data!**
- When you train the model, the machine learning model (Random Forest Regressor) only learns the *patterns* or mathematical *logic* of the weather.
- When the forecast is displayed on the dashboard, the server pulls the absolute **current moment's or latest** sensor readings (temperature, humidity, pressure) from the database and sends them to that trained model.
- The model uses its learned knowledge to analyze the current data and generates new predictions for what the temperature, humidity, and pressure will be after 1 hour (+1h), 2 hours (+2h), and 3 hours (+3h).
- **In summary:** Your model is trained only once, but as the current sensor data changes, your forecast values will also automatically update in real-time.

---

## 4. Automatic Update vs Manual Refresh
- The entire dashboard updates **completely automatically**! You never have to press the browser's refresh button.
- There is a JavaScript function named `poll()` written in the frontend (`dashboard.js` file) of the project.
- Using `setInterval`, this function requests new data from the backend (via API calls) **every 10 seconds**.
- If the ESP32 has sent new data, the dashboard's live readings, forecast values, and charts/graphs will magically update live without a page reload. This is known as a "Real-time Dashboard".

---

## 5. Dataset vs Balanced Dataset (What's the difference?)
When training a machine learning model, the balance of the data is very crucial.

*   **Full Dataset (Just "Dataset"):**
    Here, all the data available in the database is fed to the model. The problem is, in our region, the weather is mostly "Sunny", and it rains very rarely. So, if you train the model with the Full Dataset, the model becomes too accustomed to seeing "Sunny" data. Even if there's a chance of rain, it might still try to predict "Sunny". In machine learning terms, this is called **Data Imbalance or Biasing**.

*   **Balanced Dataset:**
    When you click on the "Balanced" option, the backend filters the data using a special algorithm (`get_balanced_data()`). It carefully keeps all the rare "Rainy" data from the database and randomly selects an equal number of rows from the "Sunny" and "Cloudy" data.
    **Result:** The model learns equally about all three weather conditions (Sunny, Cloudy, Rainy), making its predictions much more precise and accurate.
