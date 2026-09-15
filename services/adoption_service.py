"""
Climate Information Dissemination & Use - Farmer Adoption & Retention Tracking
Measures farmer journey: Enrollment → SMS Reception → Engagement → Retention → Behavior Change
Supports community-level dissemination via Climate Champions
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class AdoptionService:
    """Service for tracking farmer adoption of climate information"""
    
    @staticmethod
    def calculate_retention_status(adoption):
        """
        Calculate retention status based on last SMS received
        
        States:
        - pending: newly enrolled, no SMS yet
        - active: last SMS <7 days ago (engaged farmer)
        - at_risk: last SMS 7-30 days ago (needs re-engagement)
        - inactive: last SMS 30-90 days ago
        - churned: last SMS >90 days ago
        """
        if not adoption.last_sms_date:
            return 'pending'
        
        days_inactive = (datetime.utcnow() - adoption.last_sms_date).days
        
        if days_inactive < 7:
            return 'active'
        elif days_inactive < 30:
            return 'at_risk'
        elif days_inactive < 90:
            return 'inactive'
        else:
            return 'churned'
    
    @staticmethod
    def calculate_engagement_score(adoption):
        """
        Calculate farmer engagement score 0-100
        
        Scoring:
        - SMS received: max 30 points (1 point per SMS, capped at 30)
        - Behavior adoption: max 40 points (10 points per practice change)
        - Retention bonus: max 30 points (active=30, at_risk=15, inactive=5)
        """
        score = 0
        
        # SMS received: Max 30 points
        sms_score = min(adoption.sms_received_count, 30)
        score += sms_score
        
        # Behavioral adoption: Max 40 points
        behavior_score = min(adoption.behavior_changes_logged * 10, 40)
        score += behavior_score
        
        # Retention bonus: Max 30 points
        if adoption.retention_status == 'active':
            score += 30
        elif adoption.retention_status == 'at_risk':
            score += 15
        elif adoption.retention_status == 'inactive':
            score += 5
        
        return min(score, 100)
    
    @staticmethod
    def update_adoption_on_sms_send(participant_id, db, FarmerAdoption):
        """
        Called whenever SMS is sent to farmer
        Auto-updates: first_sms_date, sms_count, retention_status, engagement_score
        """
        adoption = FarmerAdoption.query.filter_by(participant_id=participant_id).first()
        
        if not adoption:
            adoption = FarmerAdoption(participant_id=participant_id)
        
        # Track first SMS if this is the first one
        if not adoption.first_sms_received:
            adoption.first_sms_received = datetime.utcnow()
            if adoption.enrollment_date:
                adoption.days_to_first_sms = (adoption.first_sms_received - adoption.enrollment_date).days
        
        # Update SMS tracking
        adoption.last_sms_date = datetime.utcnow()
        adoption.sms_received_count += 1
        adoption.days_since_last_sms = 0
        
        # Recalculate retention & engagement
        adoption.retention_status = AdoptionService.calculate_retention_status(adoption)
        adoption.engagement_score = AdoptionService.calculate_engagement_score(adoption)
        adoption.last_updated = datetime.utcnow()
        
        db.session.commit()
        logger.info(f"Updated adoption for farmer {participant_id}: engagement={adoption.engagement_score}, status={adoption.retention_status}")
        return adoption
    
    @staticmethod
    def log_behavior_adoption(participant_id, alert_type, behavior_description, reported_by, reported_by_champion_id, db, FarmerAdoption, BehaviorChangeLog):
        """
        Log when farmer changes farming practice based on climate information
        
        Example:
        - alert_type: "heavy_rain"
        - behavior_description: "Delayed fertilizer by 3 days after rain alert"
        - reported_by: "Champion John Inya"
        - reported_by_champion_id: 5
        """
        log = BehaviorChangeLog(
            participant_id=participant_id,
            alert_type=alert_type,
            behavior_description=behavior_description,
            reported_by=reported_by,
            reported_by_champion_id=reported_by_champion_id
        )
        db.session.add(log)
        
        # Update adoption record
        adoption = FarmerAdoption.query.filter_by(participant_id=participant_id).first()
        if adoption:
            adoption.behavior_changes_logged += 1
            adoption.last_behavior_change_date = datetime.utcnow()
            adoption.engagement_score = AdoptionService.calculate_engagement_score(adoption)
            adoption.last_updated = datetime.utcnow()
            logger.info(f"Logged behavior change for farmer {participant_id}: {alert_type}")
        
        db.session.commit()
        return log
    
    @staticmethod
    def get_at_risk_farmers(state, lga=None, db=None, FarmerAdoption=None):
        """
        Get list of at-risk farmers (7-30 days since last SMS)
        For SPMU re-engagement campaigns via Champions
        """
        query = FarmerAdoption.query.filter(
            FarmerAdoption.retention_status == 'at_risk'
        )
        
        if state:
            from models import Participant
            query = query.join(Participant).filter(Participant.state == state)
            if lga:
                query = query.filter(Participant.lga == lga)
        
        return query.all()
    
    @staticmethod
    def get_retention_summary(state, lga=None, db=None, FarmerAdoption=None):
        """
        Get retention dashboard summary for SPMU (state/LGA level)
        Returns: counts by status, engagement metrics, adoption rate
        """
        from sqlalchemy import func
        
        query = FarmerAdoption.query
        
        if state:
            from models import Participant
            query = query.join(Participant).filter(Participant.state == state)
            if lga:
                query = query.filter(Participant.lga == lga)
        
        total = query.count()
        if total == 0:
            return {
                'total': 0,
                'active': 0,
                'at_risk': 0,
                'inactive': 0,
                'churned': 0,
                'pending': 0,
                'adoption_rate': 0,
                'avg_engagement_score': 0,
                'avg_behavior_changes': 0
            }
        
        active = query.filter(FarmerAdoption.retention_status == 'active').count()
        at_risk = query.filter(FarmerAdoption.retention_status == 'at_risk').count()
        inactive = query.filter(FarmerAdoption.retention_status == 'inactive').count()
        churned = query.filter(FarmerAdoption.retention_status == 'churned').count()
        pending = query.filter(FarmerAdoption.retention_status == 'pending').count()
        
        avg_score = db.session.query(func.avg(FarmerAdoption.engagement_score)).select_from(FarmerAdoption)
        if state:
            from models import Participant
            avg_score = avg_score.join(Participant).filter(Participant.state == state)
        avg_score = avg_score.scalar() or 0
        
        avg_behavior = db.session.query(func.avg(FarmerAdoption.behavior_changes_logged)).select_from(FarmerAdoption)
        if state:
            from models import Participant
            avg_behavior = avg_behavior.join(Participant).filter(Participant.state == state)
        avg_behavior = avg_behavior.scalar() or 0
        
        return {
            'total': total,
            'active': active,
            'at_risk': at_risk,
            'inactive': inactive,
            'churned': churned,
            'pending': pending,
            'adoption_rate': round((active / total * 100), 1) if total > 0 else 0,
            'avg_engagement_score': round(avg_score, 1),
            'avg_behavior_changes': round(avg_behavior, 1)
        }
    
    @staticmethod
    def get_champion_impact(champion_id, db):
        """
        Get impact metrics for a Climate Champion
        Shows: farmers reached, referrals, behavior changes reported
        """
        from models import ClimateChampion, FarmerAdoption, BehaviorChangeLog
        
        champion = ClimateChampion.query.get(champion_id)
        if not champion:
            return None
        
        # Farmers referred by this champion
        referrals = db.session.query(FarmerAdoption).filter(
            FarmerAdoption.referred_by_champion_id == champion_id
        ).count()
        
        # Behavior changes reported by this champion
        behavior_reports = db.session.query(BehaviorChangeLog).filter(
            BehaviorChangeLog.reported_by_champion_id == champion_id
        ).count()
        
        # Average engagement score of referred farmers
        avg_engagement = db.session.query(func.avg(FarmerAdoption.engagement_score)).filter(
            FarmerAdoption.referred_by_champion_id == champion_id
        ).scalar() or 0
        
        return {
            'champion_id': champion_id,
            'champion_name': champion.participant.full_name if champion.participant else 'Unknown',
            'state': champion.state,
            'champion_type': champion.champion_type,
            'farmers_reached': champion.farmers_reached,
            'farmers_referred': referrals,
            'behavior_changes_reported': behavior_reports,
            'avg_referral_engagement': round(avg_engagement, 1),
            'training_sessions_conducted': champion.training_sessions_conducted
        }

