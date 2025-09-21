# KnowledgeTree - A Context-Aware Knowledge Graph

KnowledgeTree is a web application for building hierarchical knowledge bases. Unlike a standard wiki or KB, KnowledgeTree understands the parent-child relationships between articles, allowing users to export a full "context stack" for any given piece of information. This is designed for piping rich, layered context into AI tools and APIs.

It uses a file-manager-like interface for intuitive organization.

## Features

* **Hierarchical Structure**: Organize articles and folders in a tree-like structure.
* **Markdown Editor**: Write content using a simple, powerful Markdown editor.
* **Context Export**: Copy the entire chain of knowledge from the root to the current article with one click.
* **File Attachments**: Upload and attach files/images to any article.
* **API-Driven**: A clean JSON API for data retrieval and manipulation, ready for integration.

## Tech Stack

* **Backend**: Flask (Python)
* **Database**: Neo4j (Graph Database)
* **Frontend**: Vanilla JavaScript, EasyMDE, FontAwesome

## License

This project is licensed under the **GNU General Public License v3.0**. See the `LICENSE` file for details.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/ruapotato/KnowledgeTree
    cd KnowledgeTree
    ```

2.  **Install Python dependencies:**
    ```bash
    python3 -m venv pyenv
    source ./pyenv/bin/activate
    pip install -r requirements.txt 
    # (Create this file with Flask, neo4j, python-dotenv)
    ```

3.  **Setup Neo4j:**

-   **Install Neo4j on Ubuntu:** First, you need to add the Neo4j repository and its GPG key to your system to authenticate the packages.
    
    Bash
    
    ```
    # Add the GPG key
    wget -O - https://debian.neo4j.com/neotechnology.gpg.key | sudo apt-key add -
    
    # Add the official Neo4j repository
    echo 'deb https://debian.neo4j.com stable 5' | sudo tee /etc/apt/sources.list.d/neo4j.list
    
    # Update your package list and install Neo4j Community Edition
    sudo apt-get update
    sudo apt-get install neo4j -y
    sudo apt install openjdk-17-jdk -y
    (reload shell, or run su username -)
    
    ```
    
-   **Start the Neo4j Service:** Once installed, enable and start the Neo4j service.
    
    Bash
    
    ```
    sudo systemctl enable neo4j
    sudo systemctl start neo4j
    
    ```
    
-   **Set Your Initial Password:** Neo4j requires you to change the default password (`neo4j`) on your first connection. **You must do this before the Python app can connect.** Open the command-line Cypher shell:
    
    Bash
    
    ```
    cypher-shell -u neo4j -p neo4j
    
    ```
    
    At the prompt (`neo4j@neo4j>`), you will be asked to set a new password. Choose a strong one.
    
-   **Create a `.env` file:** In the project's root directory, create a `.env` file and add your credentials, using the **new password** you just set.
    
    ```
    NEO4J_URI=bolt://localhost:7687
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=your_new_super_secret_password
    ```

4.  **Run the application:**
    ```bash
    flask run --port=5001
    ```
    The application will be available at `http://127.0.0.1:5001`.
