
# AI Data Insight Generator 📊🤖

## About the Project
AI Data Insight Generator is a web application that helps users analyze CSV files and understand their data. It uses Python and AI to generate useful insights and visualizations.

## Features
- Upload CSV files for analysis
- Clean and process data
- Generate summary statistics and insights
- Create charts and visualizations
- Ask questions about your data using AI
- View results through a web interface

## Technologies Used
- Python
- Flask
- Pandas
- NumPy
- Google Gemini API
- HTML, CSS, JavaScript
- Chart.js

## Project Structure
- `app/` - Web application files
- `src/` - Data analysis and processing code
- `sample_data/` - Sample datasets
- `tests/` - Test files
- `uploads/` - Uploaded CSV files
- `requirements.txt` - Required Python libraries
- `.env.example` - Example environment configuration

## How to Run the Project

1. Clone the repository.
2. Open the project folder in VS Code.
3. Create a virtual environment:

   ```bash
   python -m venv .venv
   ```

4. Activate the environment on Windows:

   ```bash
   .venv\Scripts\activate
   ```

5. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

6. Add your Google Gemini API key to a `.env` file if required.

   ```env
   GEMINI_API_KEY=your_api_key_here
   ```

7. Run the application using its configured Flask entry point.
8. Open the local URL shown in your terminal.

## Author
Vaishnavi Jagdale
