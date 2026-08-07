"""
ai_sentiment.py — Guest Sentiment Analysis Engine
Rule-based keyword sentiment scoring on GuestFeedback records.
No external dependencies — pure Python + SQLAlchemy.
"""
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

log = logging.getLogger(__name__)


class SentimentAnalyzer:
    """Keyword-based sentiment analysis for hotel guest feedback."""

    # ------------------------------------------------------------------
    # Keyword lexicons
    # ------------------------------------------------------------------

    POSITIVE_KEYWORDS = [
        'excellent', 'amazing', 'wonderful', 'great', 'clean', 'friendly',
        'comfortable', 'spacious', 'helpful', 'perfect', 'love', 'best',
        'recommend', 'beautiful', 'delicious', 'outstanding', 'superb',
        'pleasant', 'cozy', 'warm', 'nice', 'good', 'fantastic', 'awesome',
        'polite', 'quick', 'smooth', 'peaceful', 'quiet', 'convenient',
        'fresh', 'tasty', 'welcoming', 'professional', 'attentive', 'spotless',
        'impressed', 'enjoyable', 'satisfying', 'lovely', 'charming',
    ]

    NEGATIVE_KEYWORDS = [
        'dirty', 'noisy', 'rude', 'slow', 'broken', 'smell', 'stain',
        'cockroach', 'bug', 'cold', 'hot', 'worst', 'terrible', 'awful',
        'horrible', 'disappointed', 'poor', 'bad', 'never', 'complaint',
        'disgusting', 'filthy', 'uncomfortable', 'tiny', 'cramped', 'leak',
        'mold', 'mould', 'stale', 'overpriced', 'rip-off', 'ripoff',
        'unprofessional', 'unclean', 'unpleasant', 'dangerous', 'unsafe',
        'infested', 'rusty', 'damp', 'musty', 'inedible', 'soggy',
        'ignored', 'unresponsive', 'unfriendly', 'unhelpful', 'annoying',
        'delay', 'wait', 'problem', 'issue', 'damage', 'missing',
    ]

    # Negation words that flip sentiment of the next keyword
    NEGATION_WORDS = [
        'not', "n't", 'no', 'never', 'neither', 'nobody', 'nothing',
        'nowhere', 'hardly', 'barely', 'scarcely', "wasn't", "weren't",
        "isn't", "aren't", "don't", "doesn't", "didn't", "won't",
    ]

    # Topic detection
    TOPIC_KEYWORDS = {
        'cleanliness': ['clean', 'dirty', 'stain', 'dust', 'hygiene', 'smell',
                        'cockroach', 'filthy', 'spotless', 'mold', 'mould',
                        'unclean', 'fresh', 'tidy', 'messy', 'infested', 'bug'],
        'service': ['staff', 'reception', 'friendly', 'rude', 'helpful', 'slow',
                    'response', 'polite', 'attentive', 'professional', 'check-in',
                    'checkin', 'checkout', 'front desk', 'manager', 'service',
                    'unprofessional', 'unfriendly', 'unhelpful', 'welcoming'],
        'food': ['breakfast', 'dinner', 'food', 'restaurant', 'meal', 'taste',
                 'delicious', 'menu', 'lunch', 'buffet', 'coffee', 'tea',
                 'stale', 'tasty', 'inedible', 'soggy', 'fresh'],
        'room': ['room', 'bed', 'bathroom', 'shower', 'towel', 'pillow',
                 'mattress', 'ac', 'air conditioning', 'noise', 'noisy', 'quiet',
                 'spacious', 'tiny', 'cramped', 'comfortable', 'view', 'balcony',
                 'tv', 'wifi', 'internet', 'hot water', 'leak', 'broken'],
        'value': ['price', 'expensive', 'cheap', 'worth', 'value', 'overpriced',
                  'money', 'affordable', 'cost', 'rate', 'budget', 'rip-off',
                  'ripoff', 'reasonable', 'fair'],
        'location': ['location', 'area', 'transport', 'nearby', 'access',
                     'parking', 'distance', 'convenient', 'central', 'far',
                     'close', 'metro', 'bus', 'taxi', 'airport'],
    }

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    def analyze_feedback(self, feedback):
        """Analyze a single GuestFeedback record.

        Returns: {score: -1.0 to 1.0, label, topics, keywords_found,
                  positive_found, negative_found}
        """
        scores = []
        keywords_found = []
        positive_found = []
        negative_found = []
        topics = []

        # 1. Numeric ratings -> sentiment
        rating_fields = [
            ('overall', feedback.rating),
            ('cleanliness', feedback.cleanliness),
            ('service', feedback.service),
            ('food', feedback.food),
            ('value', feedback.value),
        ]

        for name, val in rating_fields:
            if val is not None:
                # Map 1-5 to -1.0 to +1.0
                mapped = (val - 3) / 2.0
                scores.append(('rating', mapped, 2.0))  # weight 2.0

        # would_recommend as bonus signal
        if feedback.would_recommend is not None:
            scores.append(('recommend', 1.0 if feedback.would_recommend else -0.5, 1.0))

        # 2. Text keyword analysis
        comment = (feedback.comment or '').lower()
        if comment.strip():
            text_score, pos_kw, neg_kw = self._analyze_text(comment)
            if pos_kw or neg_kw:
                scores.append(('text', text_score, 1.5))
            positive_found = pos_kw
            negative_found = neg_kw
            keywords_found = pos_kw + neg_kw

            # Detect topics
            topics = self._detect_topics(comment)

        # 3. Composite weighted score
        if scores:
            total_weight = sum(w for _, _, w in scores)
            composite = sum(s * w for _, s, w in scores) / total_weight if total_weight else 0
        else:
            composite = 0

        # Clamp to [-1, 1]
        composite = max(-1.0, min(1.0, composite))

        # Label
        if composite >= 0.2:
            label = 'positive'
        elif composite <= -0.2:
            label = 'negative'
        else:
            label = 'neutral'

        return {
            'score': round(composite, 3),
            'label': label,
            'topics': topics,
            'keywords_found': keywords_found,
            'positive_found': positive_found,
            'negative_found': negative_found,
        }

    def _analyze_text(self, text):
        """Keyword-based text sentiment scoring with negation handling.
        Returns (score, positive_keywords, negative_keywords).
        """
        words = re.findall(r"[a-z]+(?:'[a-z]+)?", text.lower())
        pos_found = []
        neg_found = []

        negation_window = 0  # words remaining under negation

        for word in words:
            if word in self.NEGATION_WORDS or word.endswith("n't"):
                negation_window = 3  # next 3 words are negated
                continue

            is_negated = negation_window > 0

            if word in self.POSITIVE_KEYWORDS:
                if is_negated:
                    neg_found.append('not ' + word)
                else:
                    pos_found.append(word)
            elif word in self.NEGATIVE_KEYWORDS:
                if is_negated:
                    pos_found.append('not ' + word)
                else:
                    neg_found.append(word)

            if negation_window > 0:
                negation_window -= 1

        total = len(pos_found) + len(neg_found)
        if total == 0:
            return 0.0, pos_found, neg_found

        score = (len(pos_found) - len(neg_found)) / total
        return score, pos_found, neg_found

    def _detect_topics(self, text):
        """Detect which topics are mentioned in text."""
        text_lower = text.lower()
        found = []
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    found.append(topic)
                    break
        return found

    # ------------------------------------------------------------------
    # Dashboard aggregation
    # ------------------------------------------------------------------

    def get_dashboard_data(self, days=90):
        """Aggregate sentiment data for dashboard display.

        Returns: {
            avg_score, total_reviews, positive_pct, negative_pct, neutral_pct,
            trend: [{month, avg_score, count}],
            topic_scores: {topic: avg_score},
            recent_negative: [top 5 most negative recent reviews],
            word_cloud_data: [{word, count, sentiment}]
        }
        """
        from app.models import GuestFeedback, Reservation, Guest

        cutoff = datetime.utcnow() - timedelta(days=days)

        feedbacks = (
            GuestFeedback.query
            .filter(
                GuestFeedback.submitted_at >= cutoff,
                GuestFeedback.rating.isnot(None),
            )
            .order_by(GuestFeedback.submitted_at.desc())
            .all()
        )

        if not feedbacks:
            return {
                'avg_score': 0,
                'total_reviews': 0,
                'positive_pct': 0,
                'negative_pct': 0,
                'neutral_pct': 0,
                'trend': [],
                'topic_scores': {},
                'recent_negative': [],
                'word_cloud_data': [],
                'avg_rating': 0,
                'recommend_pct': 0,
            }

        # Analyze each feedback
        analyses = []
        for fb in feedbacks:
            a = self.analyze_feedback(fb)
            a['feedback'] = fb
            analyses.append(a)

        # Basic stats
        total = len(analyses)
        avg_score = sum(a['score'] for a in analyses) / total
        avg_rating = sum(fb.rating for fb in feedbacks) / total

        positive_count = sum(1 for a in analyses if a['label'] == 'positive')
        negative_count = sum(1 for a in analyses if a['label'] == 'negative')
        neutral_count = total - positive_count - negative_count

        recommend_count = sum(1 for fb in feedbacks if fb.would_recommend)
        recommend_pct = (recommend_count / total * 100) if total else 0

        # Trend by month
        monthly = defaultdict(lambda: {'scores': [], 'count': 0})
        for a in analyses:
            fb = a['feedback']
            month_key = fb.submitted_at.strftime('%Y-%m')
            monthly[month_key]['scores'].append(a['score'])
            monthly[month_key]['count'] += 1

        trend = []
        for month_key in sorted(monthly.keys()):
            m = monthly[month_key]
            trend.append({
                'month': month_key,
                'avg_score': round(sum(m['scores']) / len(m['scores']), 3),
                'count': m['count'],
            })

        # Topic scores
        topic_scores_agg = defaultdict(list)
        for a in analyses:
            fb = a['feedback']
            # Use category ratings if available
            if fb.cleanliness is not None:
                topic_scores_agg['cleanliness'].append((fb.cleanliness - 3) / 2.0)
            if fb.service is not None:
                topic_scores_agg['service'].append((fb.service - 3) / 2.0)
            if fb.food is not None:
                topic_scores_agg['food'].append((fb.food - 3) / 2.0)
            if fb.value is not None:
                topic_scores_agg['value'].append((fb.value - 3) / 2.0)

            # Text-based topic scoring
            for topic in a['topics']:
                topic_scores_agg[topic].append(a['score'])

        topic_scores = {}
        for topic, scores_list in topic_scores_agg.items():
            if scores_list:
                topic_scores[topic] = round(sum(scores_list) / len(scores_list), 3)

        # Ensure all topics present
        for topic in self.TOPIC_KEYWORDS:
            if topic not in topic_scores:
                topic_scores[topic] = 0

        # Recent negative reviews
        negative_analyses = [a for a in analyses if a['label'] == 'negative']
        negative_analyses.sort(key=lambda a: a['score'])
        recent_negative = []
        for a in negative_analyses[:5]:
            fb = a['feedback']
            res = fb.reservation
            guest = res.guest if res else None
            recent_negative.append({
                'feedback_id': fb.id,
                'reservation_id': fb.reservation_id,
                'guest_name': guest.name if guest else 'Unknown',
                'room_number': res.room.room_number if res and res.room else '?',
                'rating': fb.rating,
                'score': a['score'],
                'comment': fb.comment or '',
                'negative_keywords': a['negative_found'],
                'topics': a['topics'],
                'submitted_at': fb.submitted_at.strftime('%Y-%m-%d %H:%M'),
            })

        # Word cloud data
        word_counter = Counter()
        word_sentiment = {}
        for a in analyses:
            for kw in a.get('positive_found', []):
                word_counter[kw] += 1
                word_sentiment[kw] = 'positive'
            for kw in a.get('negative_found', []):
                word_counter[kw] += 1
                word_sentiment[kw] = 'negative'

        word_cloud_data = [
            {'word': w, 'count': c, 'sentiment': word_sentiment.get(w, 'neutral')}
            for w, c in word_counter.most_common(50)
        ]

        return {
            'avg_score': round(avg_score, 3),
            'avg_rating': round(avg_rating, 2),
            'total_reviews': total,
            'positive_pct': round(positive_count / total * 100, 1) if total else 0,
            'negative_pct': round(negative_count / total * 100, 1) if total else 0,
            'neutral_pct': round(neutral_count / total * 100, 1) if total else 0,
            'recommend_pct': round(recommend_pct, 1),
            'trend': trend,
            'topic_scores': topic_scores,
            'recent_negative': recent_negative,
            'word_cloud_data': word_cloud_data,
        }

    # ------------------------------------------------------------------
    # Actionable insights
    # ------------------------------------------------------------------

    def get_actionable_insights(self, days=90):
        """Generate actionable insights from sentiment data.

        Returns: list of {insight, severity, category, data}
        """
        from app.models import GuestFeedback, Reservation

        cutoff = datetime.utcnow() - timedelta(days=days)
        insights = []

        feedbacks = (
            GuestFeedback.query
            .filter(
                GuestFeedback.submitted_at >= cutoff,
                GuestFeedback.rating.isnot(None),
            )
            .order_by(GuestFeedback.submitted_at.desc())
            .all()
        )

        if not feedbacks:
            return insights

        # Split into recent half vs older half for trend detection
        mid = len(feedbacks) // 2
        if mid == 0:
            return insights

        recent = feedbacks[:mid]
        older = feedbacks[mid:]

        # --- Category trend detection ---
        categories = [
            ('cleanliness', 'Cleanliness', 'housekeeping'),
            ('service', 'Service', 'front desk'),
            ('food', 'Food', 'F&B'),
            ('value', 'Value', 'pricing'),
        ]

        for attr, display, dept in categories:
            recent_vals = [getattr(fb, attr) for fb in recent if getattr(fb, attr) is not None]
            older_vals = [getattr(fb, attr) for fb in older if getattr(fb, attr) is not None]

            if recent_vals and older_vals:
                recent_avg = sum(recent_vals) / len(recent_vals)
                older_avg = sum(older_vals) / len(older_vals)

                if older_avg > 0:
                    pct_change = ((recent_avg - older_avg) / older_avg) * 100

                    if pct_change <= -15:
                        insights.append({
                            'insight': (
                                f'{display} scores dropped {abs(pct_change):.0f}% recently '
                                f'(from {older_avg:.1f} to {recent_avg:.1f}). '
                                f'Inspect {dept} operations.'
                            ),
                            'severity': 'HIGH' if pct_change <= -25 else 'MEDIUM',
                            'category': attr,
                            'data': {
                                'recent_avg': round(recent_avg, 2),
                                'older_avg': round(older_avg, 2),
                                'change_pct': round(pct_change, 1),
                            },
                        })
                    elif pct_change >= 15:
                        insights.append({
                            'insight': (
                                f'{display} scores improved {pct_change:.0f}% recently '
                                f'(from {older_avg:.1f} to {recent_avg:.1f}). '
                                f'Great work by {dept} team!'
                            ),
                            'severity': 'LOW',
                            'category': attr,
                            'data': {
                                'recent_avg': round(recent_avg, 2),
                                'older_avg': round(older_avg, 2),
                                'change_pct': round(pct_change, 1),
                            },
                        })

        # --- Keyword clustering: find common complaints ---
        negative_feedbacks = [fb for fb in feedbacks if fb.rating and fb.rating <= 2]
        if negative_feedbacks:
            complaint_topics = Counter()
            room_complaints = defaultdict(list)

            for fb in negative_feedbacks:
                a = self.analyze_feedback(fb)
                for topic in a['topics']:
                    complaint_topics[topic] += 1
                # Track rooms mentioned in negative feedback
                res = fb.reservation
                if res and res.room:
                    room_complaints[res.room.room_number].extend(a['negative_found'])

            # Top complaint topic
            if complaint_topics:
                top_topic, top_count = complaint_topics.most_common(1)[0]
                if top_count >= 3:
                    insights.append({
                        'insight': (
                            f'{top_count} negative reviews mention "{top_topic}" issues. '
                            f'This is the most frequent complaint area — prioritize improvement.'
                        ),
                        'severity': 'HIGH' if top_count >= 5 else 'MEDIUM',
                        'category': top_topic,
                        'data': {'topic': top_topic, 'count': top_count},
                    })

            # Rooms with multiple complaints
            for room_no, keywords in room_complaints.items():
                if len(keywords) >= 3:
                    unique_kw = list(set(keywords))[:5]
                    insights.append({
                        'insight': (
                            f'Room {room_no} received {len(keywords)} negative keyword mentions: '
                            f'{", ".join(unique_kw)}. Consider inspection.'
                        ),
                        'severity': 'MEDIUM',
                        'category': 'room',
                        'data': {'room': room_no, 'keywords': unique_kw},
                    })

        # --- Weekday vs weekend pattern ---
        try:
            weekday_ratings = []
            weekend_ratings = []
            for fb in feedbacks:
                if fb.submitted_at.weekday() < 5:
                    weekday_ratings.append(fb.rating)
                else:
                    weekend_ratings.append(fb.rating)

            if weekday_ratings and weekend_ratings:
                wd_avg = sum(weekday_ratings) / len(weekday_ratings)
                we_avg = sum(weekend_ratings) / len(weekend_ratings)
                diff = abs(wd_avg - we_avg)

                if diff >= 0.5:
                    better = 'weekends' if we_avg > wd_avg else 'weekdays'
                    worse = 'weekdays' if we_avg > wd_avg else 'weekends'
                    insights.append({
                        'insight': (
                            f'Ratings are higher on {better} '
                            f'(avg {max(wd_avg, we_avg):.1f}) vs {worse} '
                            f'(avg {min(wd_avg, we_avg):.1f}). '
                            f'Consider additional training or staffing on {worse}.'
                        ),
                        'severity': 'LOW',
                        'category': 'service',
                        'data': {
                            'weekday_avg': round(wd_avg, 2),
                            'weekend_avg': round(we_avg, 2),
                        },
                    })
        except Exception as e:
            log.warning('Weekday/weekend pattern check failed: %s', e)

        # --- Overall sentiment decline warning ---
        recent_ratings = [fb.rating for fb in recent]
        older_ratings = [fb.rating for fb in older]
        if recent_ratings and older_ratings:
            recent_avg = sum(recent_ratings) / len(recent_ratings)
            older_avg = sum(older_ratings) / len(older_ratings)
            if recent_avg < older_avg - 0.5:
                insights.append({
                    'insight': (
                        f'Overall guest satisfaction is declining: '
                        f'recent avg {recent_avg:.1f} vs earlier avg {older_avg:.1f}. '
                        f'Immediate attention recommended.'
                    ),
                    'severity': 'HIGH',
                    'category': 'overall',
                    'data': {
                        'recent_avg': round(recent_avg, 2),
                        'older_avg': round(older_avg, 2),
                    },
                })

        # Sort by severity
        sev_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
        insights.sort(key=lambda i: sev_order.get(i['severity'], 9))

        return insights
