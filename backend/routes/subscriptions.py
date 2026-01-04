"""
Subscription management routes
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

from database import get_db
from models import Subscription, AuthorProfile

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


class CheckSubscriptionResponse(BaseModel):
    is_subscribed: bool
    subscription_id: Optional[str] = None
    status: Optional[str] = None


@router.get("/check/{subscriber_user_id}/{author_user_id}")
async def check_subscription(
    subscriber_user_id: str,
    author_user_id: str,
    db: Session = Depends(get_db)
):
    """Check if a user is subscribed to an author"""
    
    # Authors have access to their own content
    if subscriber_user_id == author_user_id:
        return CheckSubscriptionResponse(
            is_subscribed=True,
            subscription_id=None,
            status="self"
        )
    
    try:
        # Check for active subscription
        subscription = db.query(Subscription).filter(
            Subscription.subscriber_user_id == subscriber_user_id,
            Subscription.author_user_id == author_user_id,
            Subscription.status == 'active'
        ).first()
        
        if subscription:
            return CheckSubscriptionResponse(
                is_subscribed=True,
                subscription_id=str(subscription.id),
                status=subscription.status
            )
        
        return CheckSubscriptionResponse(
            is_subscribed=False,
            subscription_id=None,
            status=None
        )
    
    except Exception as e:
        # If UUIDs are invalid or any error, return not subscribed
        print(f"Subscription check error: {e}")
        return CheckSubscriptionResponse(
            is_subscribed=False,
            subscription_id=None,
            status=None
        )


@router.post("/create-test")
async def create_test_subscription(
    subscriber_user_id: str,
    author_user_id: str,
    db: Session = Depends(get_db)
):
    """Create a test subscription (for development only)"""
    
    # Check if already exists
    existing = db.query(Subscription).filter(
        Subscription.subscriber_user_id == subscriber_user_id,
        Subscription.author_user_id == author_user_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Subscription already exists")
    
    # Create subscription
    subscription = Subscription(
        id=uuid.uuid4(),
        subscriber_user_id=subscriber_user_id,
        author_user_id=author_user_id,
        status='active',
        amount_cents=250,
        currency='usd',
        current_period_start=datetime.utcnow()
    )
    
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    
    return {
        "success": True,
        "subscription_id": str(subscription.id),
        "message": "Test subscription created"
    }

@router.get("/stripe-test")
async def test_stripe():
    """Test Stripe connection"""
    import stripe
    from config import STRIPE_SECRET_KEY
    
    if not STRIPE_SECRET_KEY:
        return {"error": "STRIPE_SECRET_KEY not set"}
    
    stripe.api_key = STRIPE_SECRET_KEY
    
    try:
        # Try to list products (will return empty in test mode, but proves connection works)
        products = stripe.Product.list(limit=1)
        return {
            "success": True,
            "message": "Stripe connected successfully!",
            "mode": "test" if STRIPE_SECRET_KEY.startswith("sk_test") else "live"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
        
