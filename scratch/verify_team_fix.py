
import sys
from collections import Counter

def mock_uniqueness_check(leader_email, member_emails):
    all_emails = [leader_email.lower().strip()] + [email.lower().strip() for email in member_emails if email.strip()]
    email_counts = Counter(all_emails)
    duplicates = [email for email, count in email_counts.items() if count > 1]
    
    if duplicates:
        msg = f"Duplicate emails found: {', '.join(duplicates)}. Each member (including the leader) must have a unique email."
        return False, msg
    return True, "Success"

# Test cases
test_cases = [
    ("leader@test.com", ["member1@test.com", "member2@test.com"]), # Unique
    ("leader@test.com", ["leader@test.com", "member2@test.com"]), # Duplicate leader
    ("leader@test.com", ["member1@test.com", "member1@test.com"]), # Duplicate member
    ("LEADER@TEST.COM", ["leader@test.com"]), # Case sensitivity
    ("leader@test.com ", [" leader@test.com"]), # Whitespace
]

for leader, members in test_cases:
    success, msg = mock_uniqueness_check(leader, members)
    print(f"Leader: {leader}, Members: {members} -> {'PASS' if success else 'FAIL'}: {msg}")
