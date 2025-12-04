#!/bin/bash

# Check if config.py exists
if [ ! -f "config.py" ]; then
    echo "ERROR: config.py not found!"
    echo "Please create config.py from config.py.example"
    exit 1
fi

# Start the bot
python run.py
