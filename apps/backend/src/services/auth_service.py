from sqlalchemy.orm import Session
from ..models import User, UserRole
from ..schemas import UserCreate
from ..core.security import get_password_hash, verify_password
from typing import Optional

class AuthService:
    # REGEX
    EMAIL_REGEX = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    WHATSAPP_REGEX = r"^\+?\d{6,15}$" 

    # Password rules
    PASSWORD_MIN_LENGTH = 8
    PASSWORD_REGEX = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$"
    
    @staticmethod
    def get_user_by_email(db: Session, email: str) -> Optional[User]:
        """Get user by email"""
        return db.query(User).filter(User.email == email).first()
    
    @staticmethod
    def create_user(db: Session, user: UserCreate) -> User:
        """Create a new user (customer or admin)"""

        if not user.name or len(user.name.strip())<5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name must be at least 5 characters long"
            )
        
        if not user.email or not re.match(EMAIL_REGEX, user.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email format."
        )

        # Sanitize input
        name = user.name
        email = user.email
        
        # --- Validate WhatsApp ---
        whatsapp = None
        if user.whatsapp:
            if not re.match(WHATSAPP_REGEX, user.whatsapp):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid WhatsApp number format. Include country code."
            )
        whatsapp = user.whatsapp

        # --- Validate password ---
        if not user.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password is required."
            )
        if len(user.password) < PASSWORD_MIN_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password must be at least {PASSWORD_MIN_LENGTH} characters long."
            )
        if not re.match(PASSWORD_REGEX, user.password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must contain at least 1 uppercase, 1 lowercase, 1 number, and 1 special character."
            )

        # hashed password
        hashed_password = get_password_hash(user.password)
        
        # validate role
        role = UserRole(user.role) if user.role else UserRole.CUSTOMER

        # Create User
        db_user = User(
            name=name,
            email=email,
            whatsapp=whatsapp,
            password=hashed_password,
            role=role
        )
        try:
            db.add(db_user)
            db.commit()
            db.refresh(db_user)
            return db_user
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e)
            )
    
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

    