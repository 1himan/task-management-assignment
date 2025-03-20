# Task Management System

## Setup Guide

### 1. Clone the Repository
```sh
git clone https://github.com/1himan/task-management-assignment.git
cd task-management-assignment
```

### 2. Set Up Virtual Environment
```sh
python -m venv venv
```

### 3. Activate Virtual Environment
- **Windows:**
  ```sh
  venv\Scripts\activate
  ```
- **Mac/Linux:**
  ```sh
  source venv/bin/activate
  ```

### 4. Install Dependencies
```sh
pip install -r requirements.txt
```

### 5. Run the Server
```sh
uvicorn main:app --reload
```

Server runs at: [http://127.0.0.1:8000](http://127.0.0.1:8000)

