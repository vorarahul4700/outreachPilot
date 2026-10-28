# OutreachPilot Agent Guidelines & Operating Rules

## Mandatory Policy: Autonomous Conversation Logging

Without waiting for the user to explicitly ask, every conversation turn and task executed in this repository must be appended to:
[`LOCAL_BUSINESS_SCRAPER_CONVERSATION_LOG.md`](file:///c:/Users/vorar/OneDrive/Desktop/outreachPilot/LOCAL_BUSINESS_SCRAPER_CONVERSATION_LOG.md)

### Logging Protocol:
1. **At the end of every interaction turn**:
   - Append the new turn block to [`LOCAL_BUSINESS_SCRAPER_CONVERSATION_LOG.md`](file:///c:/Users/vorar/OneDrive/Desktop/outreachPilot/LOCAL_BUSINESS_SCRAPER_CONVERSATION_LOG.md).
   - Format:
     ```markdown
     ### Turn [N]: [Prompt Title Snippet]

     #### User Prompt
     ```text
     [Full user prompt]
     ```

     #### Actions & Tools Executed
     - [Action or tool used, file edited, or command run]

     #### Assistant Implementation & Final Response
     [Markdown response / summary delivered to the user]

     ---
     ```
   - Increment the `> **Total Development Turns**: [N] turns` counter in the top header.
   - Update `(Last Updated: YYYY-MM-DD)` with the current date.
   - If working under a new conversation ID, append it to `> **Source Conversation IDs**:`.
2. **Autonomous Execution**:
   - Do this proactively and automatically on every single turn without requiring the user to prompt or remind you.
