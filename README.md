
# KnowledgeTree - A Context-Aware Knowledge Graph

KnowledgeTree is a web application for building hierarchical knowledge bases. Unlike a standard wiki, KnowledgeTree understands the parent-child relationships between articles, allowing users to export a full "context stack" for any given piece of information. This is designed for piping rich, layered context into AI tools and APIs.

It uses a familiar, intuitive file-manager interface for organizing knowledge and automatically populates itself with data from external services like Freshservice and Datto RMM.

## Features ✨

-   **Automated Data Sync**: Automatically pulls in and structures company, user, and asset data from **Freshservice** and **Datto RMM**, creating a single source of truth.
    
-   **Rich Text Editor**: A beautiful WYSIWYG editor that makes writing feel natural, with a "Markdown" tab for power users who want to work with the raw source.
    
-   **Intuitive File Management**: Organize articles and folders with a classic file-browser interface:
    
    -   Single-click to select.
        
    -   Double-click to open folders or articles.
        
    -   Right-click for a full context menu (Create, Rename, Delete).
        
-   **Attached Folders (Context Linking)**: Create special "paperclip" folders that link context from one part of the tree to another, allowing for organized, reusable information.
    
-   **Hierarchical Context Export**: The core feature! Copy the entire chain of knowledge from the root to the current article with one click, perfectly formatted with path headers for AI prompts.
    
-   **File Attachments**: Upload and attach relevant files and images to any knowledge article.
    
-   **Admin Panel**: Includes tools to wipe the database, manage data puller settings, and manually trigger sync jobs.
    
-   **API-Driven**: A clean JSON API for data retrieval and manipulation, ready for integration with other systems.
    

## Automated Data Sync

KnowledgeTree includes scripts to keep your knowledge base up-to-date automatically:

-   **Freshservice Sync**:
    
    -   Pulls all companies and active users from Freshservice.
        
    -   Creates a folder for each company under `/Companies/`.
        
    -   Inside each company folder, it creates a `/Users/` directory.
        
    -   Inside the `/Users/` directory, it creates a folder for each user, containing a `Contact.md` file with their details.
        
-   **Datto RMM Sync**:
    
    -   Pulls all devices from sites in Datto RMM that have a custom `AccountNumber` variable.
        
    -   Creates a general `/Assets/` folder in each matching company's directory.
        
    -   Creates a Markdown file for each device in the `/Assets/` folder with detailed information.
        
    -   If a device's name or description matches a user, it also creates a link to the asset file in that user's folder.
        

## Tech Stack 🛠️

-   **Backend**: Flask (Python)
    
-   **Database**: Neo4j (Graph Database)
    
-   **Frontend**: Vanilla JavaScript, Toast UI Editor, FontAwesome
    
-   **Scheduler**: `schedule` library for running background jobs.
    

## License

This project is licensed under the **GNU Affero General Public License v3.0**. See the `LICENSE` file for details.

## Setup

1.  **Clone the repository:**
    
    Bash
    
    ```
    git clone https://github.com/ruapotato/KnowledgeTree
    cd KnowledgeTree
    
    ```
    
2.  **Create Environment & Install Dependencies:**
    
    Bash
    
    ```
    python3 -m venv pyenv
    source ./pyenv/bin/activate
    pip install -r requirements.txt 
    
    ```
    
3.  **Setup Neo4j:**
    
    -   Follow the official instructions for your OS. For Ubuntu:
        
        Bash
        
        ```
        # Add Neo4j GPG key and repository
        wget -O - https://debian.neo4j.com/neotechnology.gpg.key | sudo apt-key add -
        echo 'deb https://debian.neo4j.com stable 5' | sudo tee /etc/apt/sources.list.d/neo4j.list
        
        # Install Neo4j and required Java version
        sudo apt-get update
        sudo apt-get install neo4j openjdk-17-jdk -y
        
        ```
        
    -   Configure `JAVA_HOME` by adding `export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64` to your `~/.bashrc`.
        
    -   Start the Neo4j service (`sudo systemctl start neo4j`).
        
    -   Set the initial password by running `cypher-shell -u neo4j -p neo4j` and following the prompts.
        
4.  **Create `.env` file:** In the project's root directory, create a `.env` file. Add your credentials and API keys.
    
    Code snippet
    
    ```
    # Neo4j Credentials
    NEO4J_URI=bolt://localhost:7687
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=your_new_super_secret_password
    
    # Freshservice API
    FRESHSERVICE_DOMAIN=your_domain.freshservice.com
    FRESHSERVICE_API_KEY=your_freshservice_api_key
    
    # Datto RMM API
    DATTO_API_ENDPOINT=https://api.datto.com
    DATTO_API_KEY=your_datto_api_key
    DATTO_API_SECRET=your_datto_api_secret
    
    # Scheduler Intervals (Optional, defaults to 1440 minutes / 24 hours)
    FRESHSERVICE_PULL_INTERVAL=1440
    DATTO_PULL_INTERVAL=1440
    
    ```
    
5.  **Run the application:**
    
    Bash
    
    ```
    flask run --port=5001
    
    ```
    
    The application will be available at `http://127.0.0.1:5001`.
    
6.  **(Optional) First Run / Reset:** Navigate to `http://127.0.0.1:5001/admin` to wipe the database for a clean start. Then, go to `http://127.0.0.1:5001/admin/settings` to trigger the initial data syncs.
