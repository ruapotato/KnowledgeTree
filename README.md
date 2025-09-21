
# KnowledgeTree - A Context-Aware Knowledge Graph

KnowledgeTree is a web application for building hierarchical knowledge bases. Unlike a standard wiki, KnowledgeTree understands the parent-child relationships between articles, allowing users to export a full "context stack" for any given piece of information. This is designed for piping rich, layered context into AI tools and APIs.

It uses a familiar, intuitive file-manager interface for organizing knowledge.

## Features ✨

-   **Rich Text Editor**: A beautiful WYSIWYG editor that makes writing feel natural, with a "Markdown" tab for power users who want to work with the raw source.
    
-   **Intuitive File Management**: Organize articles and folders with a classic file-browser interface:
    
    -   Single-click to select.
        
    -   Double-click to open folders or articles.
        
    -   Right-click for a full context menu (Create, Rename, Delete).
        
-   **Attached Folders (Context Linking)**: Create special "paperclip" folders that link context from one part of the tree to another, allowing for organized, reusable information.
    
-   **Hierarchical Context Export**: The core feature! Copy the entire chain of knowledge from the root to the current article with one click, perfectly formatted with path headers for AI prompts.
    
-   **Human-Readable URLs**: Navigate using clean, path-based URLs (e.g., `/#/Companies/A-1/Onboarding`) with full browser back/forward button support.
    
-   **File Attachments**: Upload and attach relevant files and images to any knowledge article.
    
-   **Admin Panel**: Includes a powerful tool to wipe and re-initialize the database for a clean start.
    
-   **API-Driven**: A clean JSON API for data retrieval and manipulation, ready for integration with other systems.
    

## Tech Stack 🛠️

-   **Backend**: Flask (Python)
    
-   **Database**: Neo4j (Graph Database)
    
-   **Frontend**: Vanilla JavaScript, Toast UI Editor, FontAwesome
    

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
    
    -   **Install Neo4j on Ubuntu:** You'll need Neo4j and Java 17.
        
        Bash
        
        ```
        # Add the Neo4j GPG key and repository
        wget -O - https://debian.neo4j.com/neotechnology.gpg.key | sudo apt-key add -
        echo 'deb https://debian.neo4j.com stable 5' | sudo tee /etc/apt/sources.list.d/neo4j.list
        
        # Update and install Neo4j and required Java version
        sudo apt-get update
        sudo apt-get install neo4j openjdk-17-jdk -y
        
        ```
        
    -   **Configure `JAVA_HOME`**: Add the following to the end of your `~/.bashrc` file:
        
        Bash
        
        ```
        export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
        
        ```
        
        Then, reload your shell (`source ~/.bashrc`) or open a new terminal.
        
    -   **Start the Neo4j Service:**
        
        Bash
        
        ```
        sudo systemctl enable neo4j
        sudo systemctl start neo4j
        
        ```
        
    -   **Set Initial Password:** You **must** change the default password before the app can connect.
        
        Bash
        
        ```
        cypher-shell -u neo4j -p neo4j
        
        ```
        
        At the prompt, you will be forced to set a new password. Choose a strong one.
        
    -   **Create `.env` file:** In the project's root directory, create a `.env` file and add your credentials, using the **new password** you just set.
        
        ```
        NEO4J_URI=bolt://localhost:7687
        NEO4J_USER=neo4j
        NEO4J_PASSWORD=your_new_super_secret_password
        
        ```
        
4.  **Run the application:**
    
    Bash
    
    ```
    flask run --port=5001
    
    ```
    
    The application will be available at `http://127.0.0.1:5001`.
    
5.  **(Optional) First Run / Reset:** If you encounter any old data or issues, navigate to `http://127.0.0.1:5001/admin` to wipe the database for a clean start.
