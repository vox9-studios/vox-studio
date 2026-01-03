"""
Comments API routes
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import uuid

from database import get_db
from models import Comment, CommentLike, EpisodeLike, CommentReport, AuthorProfile

router = APIRouter(prefix="/api/comments", tags=["comments"])


@router.post("/")
async def create_comment(
    request: dict,
    db: Session = Depends(get_db)
):
    """Create a new comment or reply"""
    
    episode_id = request.get('episode_id')
    user_id = request.get('user_id')
    text = request.get('text', '').strip()
    parent_comment_id = request.get('parent_comment_id')
    
    if not episode_id or not user_id or not text:
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="Comment too long (max 2000 characters)")
    
    # Get author info
    author = db.query(AuthorProfile).filter(AuthorProfile.user_id == user_id).first()
    author_name = author.display_name if author else "Anonymous"
    author_avatar = author.avatar_url if author else None
    
    # Create comment
    comment = Comment(
        episode_id=episode_id,
        user_id=user_id,
        author_name=author_name,
        author_avatar_url=author_avatar,
        text=text,
        parent_comment_id=parent_comment_id
    )
    
    db.add(comment)
    db.commit()
    db.refresh(comment)
    
    return {
        "success": True,
        "comment": {
            "id": str(comment.id),
            "episode_id": str(comment.episode_id),
            "user_id": str(comment.user_id),
            "author_name": comment.author_name,
            "author_avatar_url": comment.author_avatar_url,
            "text": comment.text,
            "parent_comment_id": str(comment.parent_comment_id) if comment.parent_comment_id else None,
            "like_count": comment.like_count,
            "created_at": comment.created_at.isoformat(),
            "is_deleted": comment.is_deleted
        }
    }


@router.get("/{episode_id}")
async def get_comments(
    episode_id: str,
    sort: str = "newest",
    db: Session = Depends(get_db)
):
    """Get all comments for an episode"""
    
    query = db.query(Comment).filter(
        Comment.episode_id == episode_id,
        Comment.is_deleted == False
    )
    
    # Sort
    if sort == "oldest":
        query = query.order_by(Comment.created_at.asc())
    elif sort == "most_liked":
        query = query.order_by(Comment.like_count.desc(), Comment.created_at.desc())
    else:  # newest
        query = query.order_by(Comment.created_at.desc())
    
    comments = query.all()
    
    # Format response with nested structure
    comment_dict = {}
    root_comments = []
    
    # First pass: create dict
    for comment in comments:
        comment_data = {
            "id": str(comment.id),
            "episode_id": str(comment.episode_id),
            "user_id": str(comment.user_id),
            "author_name": comment.author_name,
            "author_avatar_url": comment.author_avatar_url,
            "text": comment.text,
            "parent_comment_id": str(comment.parent_comment_id) if comment.parent_comment_id else None,
            "like_count": comment.like_count,
            "created_at": comment.created_at.isoformat(),
            "replies": []
        }
        comment_dict[str(comment.id)] = comment_data
        
        if comment.parent_comment_id is None:
            root_comments.append(comment_data)
    
    # Second pass: nest replies
    for comment in comments:
        if comment.parent_comment_id:
            parent_id = str(comment.parent_comment_id)
            if parent_id in comment_dict:
                comment_dict[parent_id]["replies"].append(comment_dict[str(comment.id)])
    
    return {
        "comments": root_comments,
        "total_count": len([c for c in comments if c.parent_comment_id is None])
    }


@router.delete("/{comment_id}")
async def delete_comment(
    comment_id: str,
    user_id: str,
    db: Session = Depends(get_db)
):
    """Delete a comment (soft delete)"""
    
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # Check if user owns the comment or is episode author
    from models import GenerationJob
    episode = db.query(GenerationJob).filter(GenerationJob.id == comment.episode_id).first()
    
    if str(comment.user_id) != user_id and (not episode or episode.author_id != user_id):
        raise HTTPException(status_code=403, detail="Not authorized to delete this comment")
    
    # Soft delete
    comment.is_deleted = True
    comment.text = "[deleted]"
    db.commit()
    
    return {"success": True, "message": "Comment deleted"}


@router.post("/{comment_id}/like")
async def toggle_comment_like(
    comment_id: str,
    request: dict,
    db: Session = Depends(get_db)
):
    """Like or unlike a comment"""
    
    user_id = request.get('user_id')
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    
    # Check if already liked
    existing_like = db.query(CommentLike).filter(
        CommentLike.comment_id == comment_id,
        CommentLike.user_id == user_id
    ).first()
    
    if existing_like:
        # Unlike
        db.delete(existing_like)
        db.commit()
        return {"success": True, "liked": False}
    else:
        # Like
        like = CommentLike(comment_id=comment_id, user_id=user_id)
        db.add(like)
        db.commit()
        return {"success": True, "liked": True}


@router.post("/episodes/{episode_id}/like")
async def toggle_episode_like(
    episode_id: str,
    request: dict,
    db: Session = Depends(get_db)
):
    """Like or unlike an episode"""
    
    user_id = request.get('user_id')
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    
    # Check if already liked
    existing_like = db.query(EpisodeLike).filter(
        EpisodeLike.episode_id == episode_id,
        EpisodeLike.user_id == user_id
    ).first()
    
    if existing_like:
        # Unlike
        db.delete(existing_like)
        db.commit()
        return {"success": True, "liked": False}
    else:
        # Like
        like = EpisodeLike(episode_id=episode_id, user_id=user_id)
        db.add(like)
        db.commit()
        return {"success": True, "liked": True}


@router.get("/episodes/{episode_id}/liked")
async def check_episode_liked(
    episode_id: str,
    user_id: str,
    db: Session = Depends(get_db)
):
    """Check if user has liked an episode"""
    
    liked = db.query(EpisodeLike).filter(
        EpisodeLike.episode_id == episode_id,
        EpisodeLike.user_id == user_id
    ).first() is not None
    
    return {"liked": liked}


@router.post("/{comment_id}/report")
async def report_comment(
    comment_id: str,
    request: dict,
    db: Session = Depends(get_db)
):
    """Report a comment"""
    
    reporter_id = request.get('user_id')
    reason = request.get('reason', '').strip()
    
    if not reporter_id or not reason:
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    # Check if already reported by this user
    existing = db.query(CommentReport).filter(
        CommentReport.comment_id == comment_id,
        CommentReport.reporter_id == reporter_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="You have already reported this comment")
    
    report = CommentReport(
        comment_id=comment_id,
        reporter_id=reporter_id,
        reason=reason
    )
    
    db.add(report)
    db.commit()
    
    return {"success": True, "message": "Comment reported"}


@router.get("/reports")
async def get_comment_reports(
    author_id: str,
    db: Session = Depends(get_db)
):
    """Get all comment reports for author's episodes"""
    
    from models import GenerationJob
    
    # Get all episode IDs for this author
    episodes = db.query(GenerationJob.id).filter(GenerationJob.author_id == author_id).all()
    episode_ids = [str(e.id) for e in episodes]
    
    # Get reports for comments on these episodes
    reports = db.query(CommentReport, Comment).join(
        Comment, CommentReport.comment_id == Comment.id
    ).filter(
        Comment.episode_id.in_(episode_ids),
        CommentReport.status == "pending"
    ).all()
    
    return {
        "reports": [
            {
                "id": str(report.id),
                "comment_id": str(report.comment_id),
                "comment_text": comment.text,
                "reason": report.reason,
                "created_at": report.created_at.isoformat()
            }
            for report, comment in reports
        ]
    }
