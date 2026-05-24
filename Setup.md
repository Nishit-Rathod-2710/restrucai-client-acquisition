# Setting Up the Google Maps Lead Generator

Welcome! This guide will walk you through setting up and running the Google Maps Lead Generator project on your computer from scratch. Don't worry if you're not deeply technical—just follow these steps one by one.

---

## What You Need Before You Start

1. **Python**: You need Python installed on your computer. 
   - [Download Python here](https://www.python.org/downloads/) (Make sure to check the box that says "Add Python to PATH" during installation if you're on Windows).
2. **A Text Editor**: Like VS Code, Sublime Text, or Notepad++ to edit a configuration file.

---

## Step 1: Get Your Free API Keys

You need API keys (like passwords) to let the app talk to Google Maps Scraper and the AI that understands your English prompts.

### 1. Apify API Token (To scrape Google Maps)
1. Go to [Apify.com](https://console.apify.com/sign-up) and create a free account.
2. Once logged in, go to **Settings** (gear icon) > **Integrations**.
3. Copy your **Personal API token**. Save it somewhere safe for a moment.

### 2. OpenRouter API Key (To understand your plain English queries)
*Note: You can also use OpenAI if you prefer, but OpenRouter is easy and gives you cheap access to the latest AI models.*
1. Go to [OpenRouter.ai](https://openrouter.ai/) and sign up.
2. Click on **Keys** in the top menu and click **Create Key**. Give it any name.
3. Copy the generated Key. Save it alongside your Apify token.

---

## Step 2: Open Your Terminal

You need to run some simple commands to install the project.
- **On Windows**: Open the Start menu, type `cmd` or `powershell`, and hit Enter.
- **On Mac**: Press `Cmd + Space`, type `Terminal`, and hit Enter.

Use the `cd` command to navigate to the folder where you placed this project. For example:
```bash
cd path/to/gmaps-lead-gen
```

---

## Step 3: Set Up the Python Environment

It's best practice to create a "Virtual Environment"—a little bubble on your computer just for this project's dependencies.

Run these exact commands in your terminal:

**1. Create the virtual environment:**
```bash
python -m venv venv
```

**2. Activate the virtual environment:**
- **On Windows:**
  ```bash
  .\venv\Scripts\activate
  ```
- **On Mac/Linux:**
  ```bash
  source venv/bin/activate
  ```
*(You should now see `(venv)` at the beginning of your terminal prompt!)*

**3. Install the required packages:**
```bash
pip install -r requirements.txt
```

---

## Step 4: Add Your API Keys to the Project

The app needs to know your secret keys. 

1. Inside the project folder, look for a file named `.env`.
   - *If you don't see it, create a new text file and simply name it exactly `.env` (don't forget the dot!).*
2. Open `.env` in your text editor.
3. Paste the following text and insert the keys you got in Step 1:

```env
# Paste your Apify Token here
APIFY_API_TOKEN=your_apify_token_here

# Paste your OpenRouter API Key here (starts with 'sk-or-...')
OPENROUTER_API_KEY=your_openrouter_key_here

# Leave this blank unless you are using standard OpenAI instead of OpenRouter
OPENAI_API_KEY=

# An internal secret code for the app to run securely
FLASK_SECRET_KEY=supersecretkey_dev
```
4. Save the file and close it.

---

## Step 5: Start the Application!

Everything is ready. Make sure your terminal still has the `(venv)` prefix active, and run:

```bash
python app.py
```

You should see output telling you the server is running, like this:
```
* Running on http://127.0.0.1:5000
```

---

## Step 6: Use the App

1. Open your web browser (Chrome, Safari, Edge, etc.).
2. Go to the address: **[http://127.0.0.1:5000](http://127.0.0.1:5000)**
3. You will see the Lead Generator Dashboard.
4. Click **[ + NEW QUERY ]** and type something like: 
   *"Find 10 plumbers in Austin Texas"*
5. Click **[ EXECUTE ]**.
6. Wait for the extraction to run. Once finished, click on the result to view all the extracted leads!

**Tip for Free Emails:** Once a list is generated, you can click the **[ ⚡ ENRICH EMAILS ]** button. The app will automatically visit every business's website to hunt for their contact email—completely for free.

---

### Troubleshooting

- **"python is not recognized as an internal or external command"**: Python isn't installed properly or isn't in your system PATH. Reinstall Python and make sure to check "Add Python to PATH".
- **"ModuleNotFoundError"**: You forgot to activate your virtual environment or run `pip install -r requirements.txt`. Go back to Step 3.
- **The extraction fails instantly**: Double-check that your Apify API Token inside `.env` is correct and saved properly.
