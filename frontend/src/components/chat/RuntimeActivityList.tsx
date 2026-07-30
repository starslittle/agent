import React from 'react';
import { RuntimeActivity } from '../../lib/conversation-stream-reducer';

interface RuntimeActivityListProps {
  activities: RuntimeActivity[];
  onClose?: () => void;
}

export const RuntimeActivityList: React.FC<RuntimeActivityListProps> = ({ activities, onClose }) => {
  if (activities.length === 0) return null;

  return (
    <div className="runtime-activity-list">
      <div className="activity-header">
        <h4>Runtime Activity</h4>
        {onClose && <button onClick={onClose}>Close</button>}
      </div>
      <div className="activity-list">
        {activities.map((activity, index) => (
          <div key={activity.id} className={`activity-item ${activity.type}`}>
            <span className="activity-type">{activity.type.toUpperCase()}</span>
            <span className="activity-message">{activity.message}</span>
            {activity.thinking && <span className="thinking-indicator">思考中...</span>}
          </div>
        ))}
      </div>
    </div>
  );
};