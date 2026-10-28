"""
Copyright 2026 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import base64
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr

# --- Configuration ---
DATABASE_FILE = "db.sqlite3"
# Get APP_SECRET from environment variable.
SECRET_KEY = os.getenv(
    "APP_SECRET",
    "super-secret-key-that-should-be-changed-in-production-1234567890abcdef",
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Secret Storage",
    description="A secure cloud storage app for string secrets.",
    version="1.0.0",
)

# --- Security ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="login"
)  # tokenUrl is for OpenAPI docs, not an actual endpoint
global_salt = secrets.token_urlsafe(
    8
)  # good-enough in this simple setting to have a global salt

kdf = PBKDF2HMAC(
    algorithm=hashes.SHA256(),
    length=32,  # Fernet keys must be 32 bytes
    salt=global_salt.encode("utf-8"),  # Encode the string salt to bytes
    iterations=480000,  # A standard, secure number of iterations
)

fernet = Fernet(base64.urlsafe_b64encode(kdf.derive(global_salt.encode("utf-8"))))


def encrypt(plaintext: str) -> str:
    """
    Encrypts a string and returns a URL-safe, storable string.
    """
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(encrypted_text: str) -> str | None:
    """
    Decrypts a string. Returns the original plaintext or None if
    the token is invalid or has been tampered with.
    """
    try:
        decrypted_bytes = fernet.decrypt(encrypted_text.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken:
        # This exception is raised if the token is invalid, expired,
        # or has been tampered with.
        print("Error: Invalid or tampered token.")
        return None


# --- Database Setup ---
def get_db_connection():
    """Establishes and returns a database connection."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # This allows accessing columns by name
    return conn


def create_tables():
    """Creates the necessary database tables if they don't already exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS secrets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            secret_value TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """
    )
    conn.commit()
    conn.close()


# Ensure tables are created on application startup
@app.on_event("startup")
async def startup_event():
    create_tables()


# --- Pydantic Models ---


# Request Models
class UserRegister(BaseModel):
    email: EmailStr
    username: str
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class SecretSet(BaseModel):
    username: str
    secret: str


# Response Models
class MessageResponse(BaseModel):
    message: str


class LoginResponse(BaseModel):
    token: str
    message: str


class SecretResponse(BaseModel):
    secret: str


# Internal Models for authentication
class TokenData(BaseModel):
    username: Optional[str] = None


class UserInDB(BaseModel):
    id: int
    email: EmailStr
    username: str
    password_hash: str


# --- Utility Functions ---


def hash_password(password: str) -> str:
    """Hashes a plain-text password using bcrypt."""
    return pwd_context.hash(password + global_salt)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain-text password against a hashed password."""
    return pwd_context.verify(plain_password + global_salt, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Creates a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# --- Authentication and Authorization Dependencies ---


async def get_user_by_username(username: str) -> Optional[UserInDB]:
    """Retrieves a user from the database by username."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # CWE-89: Using parameter substitution to prevent SQL injection
    cursor.execute(
        "SELECT id, email, username, password_hash FROM users WHERE username = ?",
        (username,),
    )
    user_data = cursor.fetchone()
    conn.close()
    if user_data:
        return UserInDB(**user_data)
    return None


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    """
    Dependency to get the current authenticated user from a JWT token.
    Handles token validation and unauthorized access (CWE-284).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"message": "Invalid authentication token"},
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # CWE-703: Catch JWT errors during decoding
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user = await get_user_by_username(token_data.username)
    if user is None:
        raise credentials_exception
    return user


# --- API Endpoints ---


@app.post(
    "/register",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Authentication"],
)
async def register_user(user_data: UserRegister):
    """
    Registers a new user with email, username, and password.
    Passwords are hashed before storage (CWE-522).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if email or username already exists
    # CWE-89: Using parameter substitution
    cursor.execute(
        "SELECT id FROM users WHERE email = ? OR username = ?",
        (user_data.email, user_data.username),
    )
    existing_user = cursor.fetchone()
    if existing_user:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Email or username already in use"},
        )

    hashed_password = hash_password(user_data.password)

    try:
        # CWE-89: Using parameter substitution
        cursor.execute(
            "INSERT INTO users (email, username, password_hash) VALUES (?, ?, ?)",
            (user_data.email, user_data.username, hashed_password),
        )
        conn.commit()
    except sqlite3.Error as e:
        # CWE-703: Catch specific database errors
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"Database error during registration: {e}"},
        )
    finally:
        conn.close()

    return {"message": "Registration successful"}


@app.post("/login", response_model=LoginResponse, tags=["Authentication"])
async def login_for_access_token(user_data: UserLogin):
    """
    Authenticates a user and returns a JWT access token upon successful login.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    # CWE-89: Using parameter substitution
    cursor.execute(
        "SELECT id, email, username, password_hash FROM users WHERE email = ?",
        (user_data.email,),
    )
    user_in_db = cursor.fetchone()
    conn.close()

    # Verify user existence and password (CWE-522)
    if not user_in_db or not verify_password(
        user_data.password, user_in_db["password_hash"]
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Invalid email or password"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_in_db["username"]}, expires_delta=access_token_expires
    )
    return {"token": access_token, "message": "Login successful"}


@app.post("/set_secret", response_model=MessageResponse)
async def set_secret(
    secret_data: SecretSet, current_user: UserInDB = Depends(get_current_user)
):
    """
    Saves or updates a secret for the authenticated user.
    Ensures user can only set their own secrets (CWE-863, CWE-284).
    """
    # CWE-863, CWE-284: Authorization check - ensure the username in the request body
    # matches the username of the currently authenticated user.
    if secret_data.username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Unauthorized: Cannot set secret for another user."},
        )

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if a secret already exists for this user
        # CWE-89: Using parameter substitution
        cursor.execute("SELECT id FROM secrets WHERE user_id = ?", (current_user.id,))
        existing_secret = cursor.fetchone()

        if existing_secret:
            # Update existing secret
            # CWE-89: Using parameter substitution
            cursor.execute(
                "UPDATE secrets SET secret_value = ? WHERE user_id = ?",
                (encrypt(secret_data.secret), current_user.id),
            )
        else:
            # Insert new secret
            # CWE-89: Using parameter substitution
            cursor.execute(
                "INSERT INTO secrets (user_id, secret_value) VALUES (?, ?)",
                (current_user.id, encrypt(secret_data.secret)),
            )
        conn.commit()
    except sqlite3.Error as e:
        # CWE-703: Catch specific database errors
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"Database error when setting secret: {e}"},
        )
    finally:
        conn.close()

    return {"message": "Secret has been set successfully"}


@app.get("/get_secret", response_model=SecretResponse)
async def get_secret(username: str, current_user: UserInDB = Depends(get_current_user)):
    """
    Retrieves the secret for the authenticated user.
    Ensures user can only retrieve their own secrets (CWE-863, CWE-284).
    """
    # CWE-863, CWE-284: Authorization check - ensure the requested username
    # matches the username of the currently authenticated user.
    if username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Unauthorized: Cannot retrieve secret for another user."
            },
        )

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # CWE-89: Using parameter substitution
        cursor.execute(
            "SELECT secret_value FROM secrets WHERE user_id = ?", (current_user.id,)
        )
        secret_data = cursor.fetchone()
    except sqlite3.Error as e:
        # CWE-703: Catch specific database errors
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"Database error when getting secret: {e}"},
        )
    finally:
        conn.close()

    if secret_data:
        return {"secret": decrypt(secret_data["secret_value"])}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Secret not found for this user."},
        )


# --- Main entry point for uvicorn ---
if __name__ == "__main__":
    import uvicorn

    # Set APP_SECRET environment variable if not already set for local testing
    if "APP_SECRET" not in os.environ:
        print(
            "Warning: APP_SECRET environment variable not set. Using a default insecure key."
        )
        print("Please set APP_SECRET to a strong, random value in production.")

    uvicorn.run(app, host="0.0.0.0", port=5000)
