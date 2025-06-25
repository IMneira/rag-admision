#!/usr/bin/env python3
"""
Admin user creation script for the RAG admission system.
Creates or updates the admin user based on environment variables.
"""

import os
import sys

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from app import create_app
from app.models import User, UserRole, create_admin_user
from config import Config


def create_default_admin():
    """Create the default admin user"""
    print("=== ADMIN USER CREATION ===")
    
    app = create_app()
    
    with app.app_context():
        try:
            # Get admin credentials from config
            admin_username = Config.ADMIN_USERNAME
            admin_email = Config.ADMIN_EMAIL
            admin_password = Config.ADMIN_PASSWORD
            
            print(f"Creating admin user: {admin_username}")
            print(f"Admin email: {admin_email}")
            
            # Create or update admin user
            admin_user = create_admin_user(
                username=admin_username,
                email=admin_email,
                password=admin_password
            )
            
            print(f"✅ Admin user '{admin_user.username}' created/updated successfully!")
            print(f"   - User ID: {admin_user.id}")
            print(f"   - Role: {admin_user.role.value}")
            print(f"   - Email: {admin_user.email}")
            print(f"   - Created: {admin_user.created_at}")
            
            if admin_password == "admin123":
                print("\n⚠️  WARNING: Default password is being used!")
                print("   Please change the admin password immediately after first login.")
                print("   Set ADMIN_PASSWORD environment variable for production.")
            
            return True
            
        except Exception as e:
            print(f"❌ Error creating admin user: {e}")
            return False


def check_admin_exists():
    """Check if admin user exists"""
    app = create_app()
    
    with app.app_context():
        try:
            admin_username = Config.ADMIN_USERNAME
            admin_user = User.get_by_username(admin_username)
            
            if admin_user and admin_user.is_admin():
                print(f"✅ Admin user '{admin_username}' exists and has admin privileges")
                return True
            elif admin_user:
                print(f"⚠️  User '{admin_username}' exists but is not an admin")
                return False
            else:
                print(f"❌ Admin user '{admin_username}' does not exist")
                return False
                
        except Exception as e:
            print(f"❌ Error checking admin user: {e}")
            return False


def reset_admin_password():
    """Reset admin password"""
    app = create_app()
    
    with app.app_context():
        try:
            admin_username = Config.ADMIN_USERNAME
            new_password = Config.ADMIN_PASSWORD
            
            admin_user = User.get_by_username(admin_username)
            if not admin_user:
                print(f"❌ Admin user '{admin_username}' not found")
                return False
            
            admin_user.set_password(new_password)
            from app.db import flask_db as db
            db.session.commit()
            
            print(f"✅ Admin password reset successfully for '{admin_username}'")
            return True
            
        except Exception as e:
            print(f"❌ Error resetting admin password: {e}")
            return False


def main():
    """Main function to handle command line arguments"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Admin User Management for RAG Admission System')
    parser.add_argument('action', choices=['create', 'check', 'reset-password'], 
                       help='Action to perform: create (create/update admin), check (verify admin exists), reset-password (reset admin password)')
    
    args = parser.parse_args()
    
    print(f"Admin Username: {Config.ADMIN_USERNAME}")
    print(f"Admin Email: {Config.ADMIN_EMAIL}")
    print("=" * 50)
    
    if args.action == 'create':
        success = create_default_admin()
    elif args.action == 'check':
        success = check_admin_exists()
    elif args.action == 'reset-password':
        success = reset_admin_password()
    
    if success:
        print(f"\n✅ {args.action.capitalize()} operation completed successfully!")
    else:
        print(f"\n❌ {args.action.capitalize()} operation failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()