import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import json
import time
from PIL import Image
from io import BytesIO

# Set page configuration
st.set_page_config(
    page_title="Instagram Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        background: linear-gradient(90deg, #f09433 0%,#e6683c 25%,#dc2743 50%,#cc2366 75%,#bc1888 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .profile-header {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        padding: 2rem;
        border-radius: 15px;
        color: white;
        margin: 1rem 0;
    }
    .post-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        gap: 1rem;
        margin: 1rem 0;
    }
    .post-item {
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .cookie-input {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        border: 2px dashed #ddd;
    }
</style>
""", unsafe_allow_html=True)

class InstagramScraper:
    def __init__(self, cookies):
        """Initialize Instagram scraper with session cookies"""
        self.session = requests.Session()
        self.cookies = cookies
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'X-IG-App-ID': '936619743392459',
            'X-Requested-With': 'XMLHttpRequest',
        }
        self._setup_session()
    
    def _setup_session(self):
        """Setup session with cookies"""
        if isinstance(self.cookies, str):
            cookie_dict = {}
            for item in self.cookies.split(';'):
                if '=' in item:
                    key, value = item.strip().split('=', 1)
                    cookie_dict[key] = value
            self.cookies = cookie_dict
        
        for key, value in self.cookies.items():
            self.session.cookies.set(key, value)
    
    def get_user_profile(self, username):
        """Fetch user profile data and user_id"""
        try:
            url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
            response = self.session.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                user = data.get('data', {}).get('user', {})
                
                profile = {
                    'id': user.get('id'),
                    'username': user.get('username', username),
                    'full_name': user.get('full_name', 'N/A'),
                    'bio': user.get('biography', ''),
                    'followers': user.get('edge_followed_by', {}).get('count', 0),
                    'following': user.get('edge_follow', {}).get('count', 0),
                    'posts_count': user.get('edge_owner_to_timeline_media', {}).get('count', 0),
                    'profile_pic_url': user.get('profile_pic_url_hd', ''),
                    'is_verified': user.get('is_verified', False),
                    'is_business': user.get('is_business_account', False),
                    'category': user.get('category_name', 'Personal'),
                    'external_url': user.get('external_url', ''),
                    'is_private': user.get('is_private', False)
                }
                return profile
            else:
                st.error(f"Failed to fetch profile. Status: {response.status_code} - Body: {response.text}")
                return None
        except Exception as e:
            st.error(f"Error fetching profile: {str(e)}")
            return None
    
    def get_user_posts(self, user_id, max_posts=50):
        """Fetch user's recent posts using their user_id for better data access."""
        if not user_id:
            st.error("User ID not found. Cannot fetch posts.")
            return pd.DataFrame()
            
        try:
            url = f"https://www.instagram.com/api/v1/feed/user/{user_id}/"
            response = self.session.get(url, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                
                posts = []
                for item in items[:max_posts]:
                    caption_node = item.get('caption')
                    caption_text = caption_node.get('text', '') if caption_node else ''

                    image_candidates = item.get('image_versions2', {}).get('candidates', [{}])
                    display_url = image_candidates[0].get('url', '') if image_candidates else ''

                    post_data = {
                        'post_id': item.get('pk'),
                        'shortcode': item.get('code'),
                        'timestamp': datetime.fromtimestamp(item.get('taken_at', 0)),
                        'type': 'video' if item.get('media_type') == 2 else 'photo',
                        'likes': item.get('like_count', 0),
                        'comments': item.get('comment_count', 0),
                        'caption': caption_text[:100],
                        'display_url': display_url,
                        'thumbnail_url': display_url,
                        'is_video': item.get('media_type') == 2,
                        'video_view_count': item.get('view_count', 0) if item.get('media_type') == 2 else 0
                    }
                    posts.append(post_data)
                
                return pd.DataFrame(posts)
            else:
                st.error(f"Failed to fetch posts. Status: {response.status_code} - Body: {response.text}")
                st.warning("This could happen if your cookies are invalid or you don't follow the private user.")
                return pd.DataFrame()
        except Exception as e:
            st.error(f"Error fetching posts: {str(e)}")
            return pd.DataFrame()

def calculate_engagement_rate(likes, comments, followers):
    """Calculate engagement rate"""
    if followers > 0:
        return round(((likes + comments) / followers) * 100, 2)
    return 0

def generate_time_series_data(posts_df):
    """Generate time series analytics from posts"""
    if posts_df.empty:
        return pd.DataFrame()
    
    posts_df['date'] = posts_df['timestamp'].dt.date
    daily_stats = posts_df.groupby('date').agg({
        'likes': 'sum',
        'comments': 'sum',
        'post_id': 'count'
    }).rename(columns={'post_id': 'posts_count'})
    
    return daily_stats.reset_index()

def display_profile_section(profile_data):
    """Display profile overview section"""
    st.markdown("## 👤 Profile Overview")
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        if profile_data.get('profile_pic_url'):
            try:
                response = requests.get(profile_data['profile_pic_url'])
                img = Image.open(BytesIO(response.content))
                st.image(img, width=200)
            except:
                st.info("📷 Profile Picture")
    
    with col2:
        verified = "✅" if profile_data.get('is_verified') else ""
        business = "💼" if profile_data.get('is_business') else ""
        private = "🔒" if profile_data.get('is_private') else ""
        
        st.markdown(f"""
        <div class="profile-header">
            <h2>@{profile_data['username']} {verified} {business} {private}</h2>
            <h3>{profile_data['full_name']}</h3>
            <p>{profile_data['bio']}</p>
            <p><strong>Category:</strong> {profile_data['category']}</p>
            {f"<p>🔗 {profile_data['external_url']}</p>" if profile_data.get('external_url') else ""}
        </div>
        """, unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("👥 Followers", f"{profile_data['followers']:,}")
    with col2:
        st.metric("👤 Following", f"{profile_data['following']:,}")
    with col3:
        st.metric("📸 Posts", f"{profile_data['posts_count']:,}")
    with col4:
        follower_ratio = round(profile_data['followers'] / max(profile_data['following'], 1), 2)
        st.metric("📊 Follower Ratio", f"{follower_ratio}")

def display_posts_analytics(posts_df, profile_data):
    """Display posts analytics section"""
    if posts_df.empty:
        st.warning("No posts data available to display analytics.")
        return
    
    st.markdown("---")
    st.markdown("## 📊 Post Performance Analytics")
    
    avg_likes = posts_df['likes'].mean()
    avg_comments = posts_df['comments'].mean()
    total_engagement = posts_df['likes'].sum() + posts_df['comments'].sum()
    avg_engagement_rate = calculate_engagement_rate(
        posts_df['likes'].mean(), 
        posts_df['comments'].mean(), 
        profile_data['followers']
    )
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("❤️ Avg Likes", f"{avg_likes:,.0f}")
    with col2:
        st.metric("💬 Avg Comments", f"{avg_comments:,.0f}")
    with col3:
        st.metric("🎯 Total Engagement", f"{total_engagement:,}")
    with col4:
        st.metric("📈 Avg Engagement Rate", f"{avg_engagement_rate}%")
    
    st.markdown("### 📈 Performance Trends")
    
    col1, col2 = st.columns(2)
    
    with col1:
        fig_timeline = px.line(posts_df.sort_values('timestamp'), 
                                 x='timestamp', y=['likes', 'comments'],
                                 title='Engagement Over Time',
                                 labels={'value': 'Count', 'timestamp': 'Date'})
        fig_timeline.update_layout(hovermode='x unified')
        st.plotly_chart(fig_timeline, use_container_width=True)
    
    with col2:
        type_dist = posts_df['type'].value_counts()
        fig_type = px.pie(values=type_dist.values, names=type_dist.index,
                          title='Content Type Distribution')
        st.plotly_chart(fig_type, use_container_width=True)
    
    st.markdown("### 🔥 Top Performing Posts")
    
    col1, col2 = st.columns(2)
    
    with col1:
        top_likes = posts_df.nlargest(5, 'likes')[['shortcode', 'likes', 'comments', 'timestamp']]
        top_likes['timestamp'] = top_likes['timestamp'].dt.strftime('%Y-%m-%d')
        st.subheader("Most Liked Posts")
        st.dataframe(top_likes, use_container_width=True, hide_index=True)
    
    with col2:
        top_comments = posts_df.nlargest(5, 'comments')[['shortcode', 'likes', 'comments', 'timestamp']]
        top_comments['timestamp'] = top_comments['timestamp'].dt.strftime('%Y-%m-%d')
        st.subheader("Most Commented Posts")
        st.dataframe(top_comments, use_container_width=True, hide_index=True)
    
    st.markdown("### 📊 Engagement Distribution")
    
    fig_scatter = px.scatter(posts_df, x='likes', y='comments', 
                             size='likes', color='type',
                             hover_data=['timestamp', 'caption'],
                             title='Likes vs Comments Distribution')
    st.plotly_chart(fig_scatter, use_container_width=True)

def display_recent_posts_grid(posts_df):
    """Display recent posts in a grid"""
    st.markdown("---")
    st.markdown("## 📸 5 Most Recent Posts")
    
    if posts_df.empty:
        st.warning("No posts available to display.")
        return
    
    cols = st.columns(5)
    for idx, (_, post) in enumerate(posts_df.head(5).iterrows()):
        with cols[idx % 5]:
            if post['thumbnail_url']:
                try:
                    response = requests.get(post['thumbnail_url'])
                    img = Image.open(BytesIO(response.content))
                    st.image(img, use_container_width=True) # <-- CORRECT PARAMETER
                except:
                    st.info("🖼️ Image")
            
            st.markdown(f"""
            <div style='font-size: 0.85rem;'>
            <strong>{post['type'].upper()}</strong><br>
            ❤️ {post['likes']:,} | 💬 {post['comments']:,}<br>
            📅 {post['timestamp'].strftime('%Y-%m-%d')}<br>
            <a href='https://instagram.com/p/{post['shortcode']}' target='_blank'>View Post</a>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("---")

def display_insights(posts_df, profile_data):
    """Display AI-powered insights"""
    st.markdown("---")
    st.markdown("## 💡 Insights & Recommendations")
    
    if posts_df.empty:
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🎯 Key Insights")
        
        best_type = posts_df.groupby('type')['likes'].mean().idxmax()
        avg_engagement = calculate_engagement_rate(
            posts_df['likes'].mean(),
            posts_df['comments'].mean(),
            profile_data['followers']
        )
        
        date_range = (posts_df['timestamp'].max() - posts_df['timestamp'].min()).days
        posts_per_week = (len(posts_df) / max(date_range, 1)) * 7
        
        insights = [
            f"📊 Your average engagement rate is {avg_engagement}%",
            f"🎬 {best_type.capitalize()} content performs best on your profile",
            f"📅 You post approximately {posts_per_week:.1f} times per week",
            f"❤️ Your average post gets {posts_df['likes'].mean():.0f} likes",
            f"💬 Comments average: {posts_df['comments'].mean():.0f} per post"
        ]
        
        for insight in insights:
            st.write(f"• {insight}")
    
    with col2:
        st.subheader("🚀 Recommendations")
        
        recommendations = [
            "Post consistently to maintain audience engagement",
            f"Focus more on {best_type} content for better performance",
            "Respond to comments within the first hour for higher visibility",
            "Use relevant hashtags (5-10) for discoverability",
            "Post during peak hours when your audience is most active",
            "Create Instagram Reels for exponential reach"
        ]
        
        for rec in recommendations:
            st.write(f"• {rec}")

def main():
    st.markdown('<h1 class="main-header">📊 Instagram Analytics Dashboard</h1>', unsafe_allow_html=True)
    
    st.sidebar.title("🔐 Authentication")
    st.sidebar.markdown("---")
    
    st.sidebar.markdown("### Enter Your Instagram Cookies")
    st.sidebar.info("💡 **How to get cookies:**\n\n1. Login to Instagram on your browser\n2. Open Developer Tools (F12)\n3. Go to Application/Storage → Cookies\n4. Copy sessionid and csrftoken")
    
    cookie_input = st.sidebar.text_area(
        "Paste your cookies (format: sessionid=xxx; csrftoken=yyy)",
        placeholder="sessionid=...; csrftoken=...",
        height=100
    )
    
    username = st.sidebar.text_input("Instagram Username", placeholder="Enter username to analyze")
    
    analyze_button = st.sidebar.button("🚀 Analyze Profile", type="primary", use_container_width=True)
    
    st.sidebar.markdown("---")
    st.sidebar.warning("⚠️ **Privacy Notice:**\nYour cookies are only used for this session and are never stored. For private accounts, you must be following them.")
    
    if analyze_button:
        if not cookie_input or not username:
            st.error("❌ Please provide both cookies and username")
            return
        
        with st.spinner("🔄 Fetching Instagram data... This might take a moment."):
            try:
                scraper = InstagramScraper(cookie_input)
                
                profile_data = scraper.get_user_profile(username)
                
                if profile_data and profile_data['id']:
                    display_profile_section(profile_data)
                    
                    user_id = profile_data['id']
                    posts_df = scraper.get_user_posts(user_id, max_posts=50)
                    
                    if not posts_df.empty:
                        display_posts_analytics(posts_df, profile_data)
                        display_recent_posts_grid(posts_df)
                        display_insights(posts_df, profile_data)
                        
                        st.markdown("---")
                        st.markdown("### 💾 Export Data")
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            csv = posts_df.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                "📥 Download Posts Data (CSV)",
                                csv,
                                f"{username}_posts_data.csv",
                                "text/csv",
                                use_container_width=True
                            )
                        
                        with col2:
                            clean_profile_data = {k: v for k, v in profile_data.items() if v is not None}
                            profile_json = json.dumps(clean_profile_data, indent=2)
                            st.download_button(
                                "📥 Download Profile Data (JSON)",
                                profile_json,
                                f"{username}_profile_data.json",
                                "application/json",
                                use_container_width=True
                            )
                    else:
                        st.warning("⚠️ Could not fetch posts. The account might be private and you may not be following them, or the cookies are invalid.")
                else:
                    st.error("❌ Could not fetch profile data. Please check the username and your cookies, then try again.")
                    
            except Exception as e:
                st.error(f"❌ An unexpected error occurred: {str(e)}")
                st.info("💡 Make sure your cookies are valid and the account is accessible.")
    
    else:
        st.markdown("""
        <div style="text-align: center; padding: 3rem;">
            <h2>Welcome to Instagram Analytics Dashboard! 🎉</h2>
            <p style="font-size: 1.2rem; color: #666; margin: 2rem 0;">
                Analyze any Instagram profile with detailed metrics and insights
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("""
            ### 📊 Profile Analytics
            - Complete profile overview
            - Follower & engagement metrics
            - Account insights
            """)
        with col2:
            st.markdown("""
            ### 📈 Post Performance
            - Recent posts analysis
            - Engagement tracking
            - Works with private accounts you follow
            """)
        with col3:
            st.markdown("""
            ### 💡 Smart Insights
            - AI recommendations
            - Content performance
            - Content optimization tips
            """)
        
        st.markdown("---")
        st.markdown("""
        ### 🔒 How to Get Your Cookies:
        
        1. **Login to Instagram** on your web browser
        2. **Open Developer Tools** (Press F12 or Right-click → Inspect)
        3. Go to **Application** tab (Chrome) or **Storage** tab (Firefox)
        4. Click on **Cookies** → Select `https://www.instagram.com`
        5. Find and copy the values for `sessionid` and `csrftoken`
        6. Format them like this: `sessionid=YOUR_VALUE; csrftoken=YOUR_VALUE`
        7. Paste in the sidebar and start analyzing!
        """)

if __name__ == "__main__":
    main()