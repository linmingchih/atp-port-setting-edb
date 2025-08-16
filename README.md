# Port Setting Web Service

This is a web-based tool for setting ports on `.aedb` files.

## Features

*   Upload a `.aedb.zip` file.
*   Automatically extract component and net information.
*   Provides a user-friendly interface for setting ports in two modes:
    *   **Component Mode**: Select a component and then select the nets to create ports.
    *   **Net Mode**: Select a net and then select the components to create ports.
*   Download the updated `.aedb` file with the new ports.

## Environment Requirements

*   Python 3.x
*   Windows Operating System

## How to Start

1.  Ensure you have Python 3.x installed and it is added to your system's PATH.
2.  Double-click on the `run.bat` file.

This will:
*   Create a Python virtual environment (`.venv`) if it doesn't exist.
*   Install the required Python modules.
*   Start the web server.
*   Open the application in your default web browser.

## Operating Process

1.  **Upload**: Click the "Browse" button and select your `.aedb.zip` file.
2.  **Set Ports**:
    *   Use the "Component Mode" or "Net Mode" to select the desired components and nets.
    *   Click the "Add Ports" button to add the ports to the list.
    *   You can adjust the impedance (Z0) for each port in the table.
3.  **Download**: Once you have finished setting all the ports, click the "Download updated .aedb" button to download the modified `.aedb.zip` file.
