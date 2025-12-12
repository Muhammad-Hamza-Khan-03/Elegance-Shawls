from sqlalchemy.orm import Session
from ..models import User
from typing import List, Optional

class UserService:
    @staticmethod
    def get_all_users(db: Session) -> List[User]:
        """Get all users"""
        return db.query(User).all()
    
    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
        """Get a user by ID"""
        return db.query(User).filter(User.id == user_id).first()

