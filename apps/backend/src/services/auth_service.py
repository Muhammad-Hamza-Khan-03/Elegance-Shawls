from sqlalchemy.orm import Session
from ..models import User, UserRole
from ..schemas import UserCreate
from ..core.security import get_password_hash, verify_password
from typing import Optional

class AuthService:
    @staticmethod
    def get_user_by_email(db: Session, email: str) -> Optional[User]:
        """Get user by email"""
        return db.query(User).filter(User.email == email).first()
    
    @staticmethod
    def create_user(db: Session, user: UserCreate) -> User:
        """Create a new user (customer or admin)"""

        # TODO: Add email,password,... validations

        hashed_password = None
        if user.password:
            hashed_password = get_password_hash(user.password)
        
        db_user = User(
            name=user.name,
            email=user.email,
            whatsapp=user.whatsapp,
            password=hashed_password,
            role=UserRole(user.role) if user.role else UserRole.CUSTOMER
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    
    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password"""
        user = AuthService.get_user_by_email(db, email)
        if not user:
            return None
        if user.password is None:  # Customer without password
            return None
        if not verify_password(password, str(user.password)):
            return None
        return user
    
    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
        """Get user by ID"""
        return db.query(User).filter(User.id == user_id).first()

    