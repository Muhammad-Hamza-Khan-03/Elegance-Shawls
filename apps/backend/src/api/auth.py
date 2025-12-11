from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.security import create_access_token, get_current_user
from ..core.redis import get_redis
from ..schemas import UserCreate, UserLoginWithCart, UserResponse, Token
from ..services.auth_service import AuthService
from datetime import timedelta
from ..core.config import settings
from ..services.cart_service import CartService

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate, db: Session = Depends(get_db)):
    """Register a new user (customer or admin)"""
    # Check if user already exists
    existing_user = AuthService.get_user_by_email(db, user.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create user
    db_user = AuthService.create_user(db, user)
    return db_user

@router.post("/login", response_model=Token)
def login(
    user_credentials: UserLoginWithCart,
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis),
):
    """Login user and return JWT token"""
    user = AuthService.authenticate_user(db, user_credentials.email, user_credentials.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role.value},
        expires_delta=access_token_expires
    )

    # Merge guest cart; this is fast and keeps cart consistency at login time.
    if user_credentials.guest_cart_items:
        cart_service = CartService(redis_client)
        cart_service.merge_guest_cart(user.id, user_credentials.guest_cart_items, db)
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user = Depends(get_current_user)):
    """Get current logged-in user info"""
    return current_user     