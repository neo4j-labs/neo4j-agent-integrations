import { DiagnosticRecord } from './gql-constants';
interface NotificationPosition {
    offset?: number;
    line?: number;
    column?: number;
}
type NotificationSeverityLevel = 'WARNING' | 'INFORMATION' | 'UNKNOWN';
/**
 * @typedef {'WARNING' | 'INFORMATION' | 'UNKNOWN'} NotificationSeverityLevel
 */
/**
 * Constants that represents the Severity level in the {@link GqlStatusObject}
 */
declare const notificationSeverityLevel: {
    [key in NotificationSeverityLevel]: key;
};
/**
 * @deprecated use {@link NotificationClassification} instead.
 */
type NotificationCategory = 'HINT' | 'UNRECOGNIZED' | 'UNSUPPORTED' | 'PERFORMANCE' | 'TOPOLOGY' | 'SECURITY' | 'DEPRECATION' | 'GENERIC' | 'SCHEMA' | 'UNKNOWN';
/**
 * @typedef {'HINT' | 'UNRECOGNIZED' | 'UNSUPPORTED' |'PERFORMANCE' | 'TOPOLOGY' | 'SECURITY' | 'DEPRECATION' | 'GENERIC' | 'SCHEMA' | 'UNKNOWN' } NotificationCategory
 */
/**
 * Constants that represents the Category in the {@link Notification}
 * @deprecated use {@link notificationClassification} instead.
 */
declare const notificationCategory: {
    [key in NotificationCategory]: key;
};
type NotificationClassification = NotificationCategory;
/**
 * @typedef {NotificationCategory} NotificationClassification
 */
/**
 * Constants that represents the Classification in the {@link GqlStatusObject}
 * @type {notificationCategory}
 */
declare const notificationClassification: {
    UNKNOWN: "UNKNOWN";
    HINT: "HINT";
    UNRECOGNIZED: "UNRECOGNIZED";
    UNSUPPORTED: "UNSUPPORTED";
    PERFORMANCE: "PERFORMANCE";
    TOPOLOGY: "TOPOLOGY";
    SECURITY: "SECURITY";
    DEPRECATION: "DEPRECATION";
    GENERIC: "GENERIC";
    SCHEMA: "SCHEMA";
};
/**
 * Class for Cypher notifications
 * @access public
 * @deprecated has been superceded by {@link GqlStatusObject}
 */
declare class Notification {
    code: string;
    title: string;
    description: string;
    position: NotificationPosition | {};
    severityLevel: NotificationSeverityLevel;
    category: NotificationCategory;
    rawSeverityLevel: string;
    rawCategory?: string;
    /**
     * Create a Notification instance
     * @constructor
     * @param {Object} notification - Object with notification data
     */
    constructor(notification: any);
}
/**
 * Representation for GqlStatusObject found when executing a query.
 * <p>
 * This object represents a status of query execution.
 *
 * @public
 */
declare class GqlStatusObject {
    readonly gqlStatus: string;
    readonly statusDescription: string;
    readonly diagnosticRecord: DiagnosticRecord;
    readonly position?: NotificationPosition;
    readonly severity: NotificationSeverityLevel;
    readonly rawSeverity?: string;
    readonly classification: NotificationClassification;
    readonly rawClassification?: string;
    readonly isNotification: boolean;
    /**
     *
     * @param rawGqlStatusObject
     * @private
     */
    constructor(rawGqlStatusObject: any);
    /**
     * The json string representation of the diagnostic record.
     * The goal of this method is provide a serialized object for human inspection.
     *
     * @type {string}
     * @public
     */
    get diagnosticRecordAsJsonString(): string;
}
/**
 *
 * @private
 * @param status
 * @returns {Notification|undefined}
 */
declare function polyfillNotification(status: any): Notification | undefined;
/**
 * @private
 * @param notification
 * @returns {GqlStatusObject}
 */
declare function polyfillGqlStatusObject(notification: any): GqlStatusObject;
/**
 *
 * @private
 * @param metadata
 * @returns
 */
declare function buildGqlStatusObjectFromMetadata(metadata: any): [GqlStatusObject, ...GqlStatusObject[]];
/**
 *
 * @private
 * @param metadata
 * @returns
 */
declare function buildNotificationsFromMetadata(metadata: any): Notification[];
export default GqlStatusObject;
export { notificationSeverityLevel, notificationCategory, notificationClassification, Notification, GqlStatusObject, polyfillGqlStatusObject, polyfillNotification, buildGqlStatusObjectFromMetadata, buildNotificationsFromMetadata };
export type { NotificationPosition, NotificationSeverityLevel, NotificationCategory, NotificationClassification };
