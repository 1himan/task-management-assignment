from fastapi import FastAPI, Depends, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from typing import List, Optional
import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
from fastapi.responses import JSONResponse, Response
from fastapi.security import OAuth2PasswordBearer
from enum import Enum
import redis
import json
import os

# FastAPI App
app = FastAPI()

# MongoDB Connection
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "taskdb"

client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]

# Get Redis details from environment variables
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Connect to Redis
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

# Password Hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Secret Key
SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 1  # 1 hour expiration

# OAuth2 Scheme for Token Authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


# Task Status & Priority Enum
class StatusEnum(str, Enum):
    pending = "pending"
    completed = "completed"


class PriorityEnum(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


# User Model
class User(BaseModel):
    username: str
    password: str


# Task Model
class TaskSchema(BaseModel):
    title: str
    description: Optional[str] = None
    status: StatusEnum  # Enum Validation
    priority: PriorityEnum  # Enum Validation


# Function to Generate JWT Token
def create_jwt_token(username: str):
    token_data = {"sub": username, "exp": datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)}
    return jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)


# Function to Extract & Decode JWT Token
def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# Register User & Assign Token Immediately
@app.post("/register")
async def register(user: User, response: Response):
    user.password = pwd_context.hash(user.password)

    existing_user = await db.users.find_one({"username": user.username})
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")

    await db.users.insert_one(user.dict())

    token = create_jwt_token(user.username)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_HOURS * 3600,  # Convert hours to seconds
        samesite="Lax"
    )

    return JSONResponse(
        content={"message": "User registered successfully", "access_token": token},
        status_code=201
    )


# Login User & Assign Token
@app.post("/login")
async def login(user: User, response: Response):
    db_user = await db.users.find_one({"username": user.username})
    if not db_user or not pwd_context.verify(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_jwt_token(user.username)

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        samesite="Lax"
    )

    return JSONResponse(
        content={"message": "User logged in successfully", "access_token": token},
        status_code=201
    )


# Logout User (Clear Cookie)
@app.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Logged out successfully"}


# Create Task
@app.post("/tasks")
async def create_task(task: TaskSchema):
    task_dict = task.dict()
    task_dict["created_at"] = datetime.utcnow()
    result = await db.tasks.insert_one(task_dict)

    # Clear Cache (to prevent stale data)
    # redis_client.delete("tasks")

    return {"message": "Task created", "task_id": str(result.inserted_id)}


# Get All Tasks (With Redis Caching)
@app.get("/tasks", response_model=List[TaskSchema])
async def get_tasks(status: Optional[StatusEnum] = None, priority: Optional[PriorityEnum] = None):
    # Check if data exists in cache
    cached_tasks = redis_client.get("tasks")
    if cached_tasks:
        print("Cache Hit - And this fucking runs")
        return json.loads(cached_tasks)

    query = {}
    if status:
        query["status"] = status.value
    if priority:
        query["priority"] = priority.value

    # Fetch tasks from MongoDB
    tasks = await db.tasks.find(query).to_list(100)

    # Convert MongoDB ObjectId and datetime to JSON serializable types
    for task in tasks:
        task["_id"] = str(task["_id"])  # Convert ObjectId to string
        task["created_at"] = task["created_at"].isoformat()  # Convert datetime to string

    # Store in Redis cache (expires in 60 seconds)
    redis_client.setex("tasks", 60, json.dumps(tasks))

    return tasks

# Update Task
@app.put("/tasks/{task_id}")
async def update_task(task_id: str, task: TaskSchema):
    result = await db.tasks.update_one({"_id": task_id}, {"$set": task.dict()})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")

    # Clear Cache (to prevent stale data)
    redis_client.delete("tasks")

    return {"message": "Task updated"}


# Delete Task
@app.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    result = await db.tasks.delete_one({"_id": task_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")

    # Clear Cache (to prevent stale data)
    redis_client.delete("tasks")

    return {"message": "Task deleted"}


# Get User Info from Token
@app.get("/user")
async def get_user(username: str = Depends(get_current_user)):
    user = await db.users.find_one({"username": username})
    if user:
        return {"message": f"Hello {username}, welcome back!"}
    return {"message": "User not found"}


# Root Route
@app.get("/")
async def root():
    return {"Hello World": "Welcome to FastAPI Task Manager! 🚀"}