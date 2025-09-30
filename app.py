import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import requests
import json
from PIL import Image
from io import BytesIO
import google.generativeai as genai
import os
from dotenv import load_dotenv

# Loads variables from .env file
load_dotenv()
api_key = os.getenv("API_KEY")

# Set page configuration
st.set_page_config(
    page_title="Instagram Analytics AI Dashboard",
    page_icon="✨",
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
    .profile-header {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        padding: 2rem;
        border-radius: 15px;
        color: white;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

class InstagramScraper:
    def __init__(self, cookies):
        self.session = requests.Session()
        self.cookies = cookies
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'X-IG-App-ID': '936619743392459',
        }
        self._setup_session()
    
    def _setup_session(self):
        if isinstance(self.cookies, str):
            cookie_dict = {item.strip().split('=', 1)[0]: item.strip().split('=', 1)[1] for item in self.cookies.split(';') if '=' in item}
            self.cookies = cookie_dict
        for key, value in self.cookies.items():
            self.session.cookies.set(key, value)
    
    def get_user_profile(self, username):
        try:
            url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
            response = self.session.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                user = response.json().get('data', {}).get('user', {})
                return {
                    'id': user.get('id'),
                    'username': user.get('username', username),
                    'full_name': user.get('full_name', 'N/A'),
                    'bio': user.get('biography', ''),
                    'followers': user.get('edge_followed_by', {}).get('count', 0),
                    'following': user.get('edge_follow', {}).get('count', 0),
                    'posts_count': user.get('edge_owner_to_timeline_media', {}).get('count', 0),
                    'profile_pic_url': user.get('profile_pic_url_hd', ''),
                    'is_private': user.get('is_private', False),
                    'category': user.get('category_name', 'Personal'),
                }
            else:
                st.error(f"Failed to fetch profile. Status: {response.status_code}")
                return None
        except Exception as e:
            st.error(f"Error fetching profile: {str(e)}")
            return None
    
    def get_user_posts(self, user_id, max_posts=50):
        if not user_id: return pd.DataFrame()
        try:
            url = f"https://www.instagram.com/api/v1/feed/user/{user_id}/"
            response = self.session.get(url, headers=self.headers, timeout=15)
            if response.status_code == 200:
                items = response.json().get('items', [])
                posts = []
                for item in items[:max_posts]:
                    caption_node = item.get('caption')
                    posts.append({
                        'shortcode': item.get('code'),
                        'timestamp': datetime.fromtimestamp(item.get('taken_at', 0)),
                        'type': 'video' if item.get('media_type') == 2 else 'photo',
                        'likes': item.get('like_count', 0),
                        'comments': item.get('comment_count', 0),
                        'caption': caption_node.get('text', '') if caption_node else '',
                        'thumbnail_url': item.get('image_versions2', {}).get('candidates', [{}])[0].get('url', '')
                    })
                return pd.DataFrame(posts)
            else:
                st.error(f"Failed to fetch posts. Status: {response.status_code}")
                return pd.DataFrame()
        except Exception as e:
            st.error(f"Error fetching posts: {str(e)}")
            return pd.DataFrame()

def calculate_engagement_rate(likes, comments, followers):
    if followers > 0:
        return round(((likes + comments) / followers) * 100, 2)
    return 0

def display_profile_section(profile_data, session):
    st.markdown("## 👤 Profile Overview")
    col1, col2 = st.columns([1, 3])
    with col1:
        if profile_data.get('profile_pic_url'):
            try:
                response = session.get(profile_data['profile_pic_url'])
                response.raise_for_status()
                img = Image.open(BytesIO(response.content))
                st.image(img, width=200)
            except Exception as e:
                st.warning(f"Could not load profile picture.")
    
    with col2:
        private = "🔒" if profile_data.get('is_private') else ""
        st.markdown(f"""
        <div class="profile-header">
            <h2>@{profile_data['username']} {private}</h2>
            <h3>{profile_data['full_name']}</h3>
            <p>{profile_data['bio']}</p>
            <p><strong>Category:</strong> {profile_data['category']}</p>
        </div>
        """, unsafe_allow_html=True)
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("👥 Followers", f"{profile_data['followers']:,}")
    c2.metric("👤 Following", f"{profile_data['following']:,}")
    c3.metric("📸 Posts", f"{profile_data['posts_count']:,}")
    follower_ratio = round(profile_data['followers'] / max(profile_data['following'], 1), 2)
    c4.metric("📊 Follower Ratio", f"{follower_ratio}")

def display_posts_analytics(posts_df, profile_data):
    if posts_df.empty: return
    st.markdown("---")
    st.markdown("## 📊 Post Performance Analytics")

    avg_likes = posts_df['likes'].mean()
    avg_comments = posts_df['comments'].mean()
    avg_engagement_rate = calculate_engagement_rate(avg_likes, avg_comments, profile_data['followers'])

    c1, c2, c3 = st.columns(3)
    c1.metric("❤️ Avg Likes", f"{avg_likes:,.0f}")
    c2.metric("💬 Avg Comments", f"{avg_comments:,.0f}")
    c3.metric("📈 Avg Engagement Rate", f"{avg_engagement_rate}%")

    st.markdown("### 📈 Performance Trends")
    graph_col1, graph_col2 = st.columns(2)

    with graph_col1:
        fig_timeline = px.line(posts_df.sort_values('timestamp'), 
                                 x='timestamp', y=['likes', 'comments'],
                                 title='Engagement Over Time',
                                 labels={'value': 'Count', 'timestamp': 'Date'})
        fig_timeline.update_layout(hovermode='x unified')
        st.plotly_chart(fig_timeline, use_container_width=True)
    
    with graph_col2:
        type_dist = posts_df['type'].value_counts()
        fig_type = px.pie(values=type_dist.values, names=type_dist.index,
                          title='Content Type Distribution')
        st.plotly_chart(fig_type, use_container_width=True)

    st.markdown("### 🔥 Top Performing Content (by Engagement)")
    table_col1, table_col2 = st.columns(2)
    
    photos_df = posts_df[posts_df['type'] == 'photo'].copy()
    videos_df = posts_df[posts_df['type'] == 'video'].copy()

    with table_col1:
        st.subheader("🏆 Top 5 Photo Posts")
        if not photos_df.empty:
            photos_df['engagement'] = photos_df['likes'] + photos_df['comments']
            top_photos = photos_df.nlargest(5, 'engagement')
            top_photos['url'] = "https://instagram.com/p/" + top_photos['shortcode']
            st.dataframe(top_photos[['url', 'likes', 'comments', 'engagement']], hide_index=True, use_container_width=True,
                         column_config={"url": st.column_config.LinkColumn("Post", display_text="🔗 View"), "likes": "❤️", "comments": "💬", "engagement": "🎯"})
    with table_col2:
        st.subheader("🎬 Top 5 Video Posts")
        if not videos_df.empty:
            videos_df['engagement'] = videos_df['likes'] + videos_df['comments']
            top_videos = videos_df.nlargest(5, 'engagement')
            top_videos['url'] = "https://instagram.com/p/" + top_videos['shortcode']
            st.dataframe(top_videos[['url', 'likes', 'comments', 'engagement']], hide_index=True, use_container_width=True,
                         column_config={"url": st.column_config.LinkColumn("Post", display_text="🔗 View"), "likes": "❤️", "comments": "💬", "engagement": "🎯"})

    st.markdown("### 📊 Engagement Distribution")
    fig_scatter = px.scatter(posts_df, x='likes', y='comments', 
                             size='likes', color='type',
                             hover_data=['timestamp', 'caption'],
                             title='Likes vs Comments Distribution')
    st.plotly_chart(fig_scatter, use_container_width=True)

def display_recent_posts_grid(posts_df, session):
    if posts_df.empty: return
    st.markdown("---")
    st.markdown("## 📸 5 Most Recent Posts")
    cols = st.columns(5)
    for idx, (_, post) in enumerate(posts_df.head(5).iterrows()):
        with cols[idx % 5]:
            if post['thumbnail_url']:
                try:
                    response = session.get(post['thumbnail_url'])
                    response.raise_for_status()
                    img = Image.open(BytesIO(response.content))
                    st.image(img)
                except Exception:
                    st.warning("Image link broken.")
            st.markdown(f"❤️ {post['likes']:,} | 💬 {post['comments']:,}<br><a href='https://instagram.com/p/{post['shortcode']}' target='_blank'>View Post</a>", unsafe_allow_html=True)
            st.markdown("---")

def display_gemini_analysis(api_key, profile_data, posts_df):
    if posts_df.empty: return
    
    st.markdown("---")
    st.markdown("## 🤖 AI-Powered Analysis")

    try:
        genai.configure(api_key=api_key)
        # Corrected model name to a valid and efficient one
        model = genai.GenerativeModel('gemini-2.5-flash')
    except Exception as e:
        st.error(f"Error configuring Gemini API: {e}")
        st.warning("Please ensure you have a valid Gemini API key in your .env file.")
        return

    with st.spinner("✨ InstaAI is analyzing your profile... This may take a moment."):
        profile_summary = f"Username: @{profile_data['username']}, Followers: {profile_data['followers']}, Following: {profile_data['following']}, Posts: {profile_data['posts_count']}, Bio: '{profile_data['bio']}'"
        
        posts_df['engagement'] = posts_df['likes'] + posts_df['comments']
        avg_likes = posts_df['likes'].mean()
        avg_comments = posts_df['comments'].mean()
        
        top_posts_summary = posts_df.nlargest(3, 'engagement')[['caption', 'likes', 'comments', 'type']].to_string()
        
        prompt = f"""
        As an expert Instagram marketing strategist, analyze the following data for the user '{profile_data['username']}' and provide actionable recommendations. The user's goal is to grow their account and increase engagement.

        **Profile Data:**
        {profile_summary}

        **Recent Post Performance Summary:**
        - Average Likes per post: {avg_likes:.0f}
        - Average Comments per post: {avg_comments:.0f}
        - Their top 3 most engaging recent posts are:
        {top_posts_summary}

        **Your Task:**
        Based on all the data provided, generate a concise and encouraging report in Markdown format. Address the following sections:

        ### 📈 Overall Performance Summary
        A brief, 2-3 sentence paragraph summarizing the account's current state and health.

        ### ✅ What's Working Well
        3-4 bullet points identifying successful patterns based on their top posts and stats. What content themes or formats are resonating with their audience?

        ### 💡 Areas for Improvement
        3-4 bullet points on potential weaknesses or missed opportunities. Are certain post types underperforming? Is their bio optimized?

        ### 🚀 Actionable Recommendations
        A numbered list of 5 concrete, creative, and strategic steps the user can take in the next 2 weeks to improve their account. Make these specific to the user's data.

        ### ✍️ Content Ideas
        3 fresh and specific content ideas that expand on what's already working for them.
        """

        try:
            response = model.generate_content(prompt)
            st.markdown(response.text)
        except Exception as e:
            st.error(f"An error occurred while generating the analysis: {e}")
            st.info("The model may be overloaded, or there might be an issue with the prompt data. Please try again.")

def main():
    st.markdown('<h1 class="main-header">✨ Instagram AI Analytics Dashboard</h1>', unsafe_allow_html=True)
    
    st.sidebar.title("🔐 Authentication")
    st.sidebar.markdown("---")
    
    st.sidebar.markdown("### Instagram Cookies")
    st.sidebar.info("Login to Instagram, open DevTools (F12), go to Application → Cookies, and copy your `sessionid`.")
    cookie_input = st.sidebar.text_area("Paste your cookies (e.g., sessionid=...)", height=100)
    
    st.sidebar.markdown("---")
    username = st.sidebar.text_input("Instagram Username to Analyze", placeholder="e.g., instagram")
    
    analyze_button = st.sidebar.button("🚀 Analyze Profile", type="primary", use_container_width=True)
    
    if analyze_button:
        if not cookie_input or not username:
            st.error("❌ Please provide both your cookies and a username.")
            return
        
        with st.spinner("🔄 Fetching Instagram data..."):
            scraper = InstagramScraper(cookie_input)
            profile_data = scraper.get_user_profile(username)
            
            if profile_data and profile_data['id']:
                display_profile_section(profile_data, scraper.session)
                
                posts_df = scraper.get_user_posts(profile_data['id'], max_posts=50)
                
                if not posts_df.empty:
                    display_posts_analytics(posts_df, profile_data)
                    display_recent_posts_grid(posts_df, scraper.session)
                    
                    # ## --- MODIFIED LOGIC TO USE .env API KEY --- ##
                    if api_key:
                        display_gemini_analysis(api_key, profile_data, posts_df)
                    else:
                        st.warning("⚠️ Gemini API key not found in .env file. AI analysis is disabled.")
                else:
                    st.warning("⚠️ Could not fetch posts. Account might be private or cookies may be invalid.")
            else:
                st.error("❌ Could not fetch profile data. Check cookies and username.")
    else:
        st.info("Enter your credentials in the sidebar and click 'Analyze Profile' to begin.")

if __name__ == "__main__":
    main()