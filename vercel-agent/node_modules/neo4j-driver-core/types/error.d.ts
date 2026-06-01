/**
 * Copyright (c) "Neo4j"
 * Neo4j Sweden AB [https://neo4j.com]
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
import { DiagnosticRecord } from './gql-constants';
export type ErrorClassification = 'DATABASE_ERROR' | 'CLIENT_ERROR' | 'TRANSIENT_ERROR' | 'UNKNOWN';
/**
 * Error code representing complete loss of service. Used by {@link Neo4jError#code}.
 * @type {string}
 */
declare const SERVICE_UNAVAILABLE: string;
/**
 * Error code representing transient loss of service. Used by {@link Neo4jError#code}.
 * @type {string}
 */
declare const SESSION_EXPIRED: string;
/**
 * Error code representing serialization/deserialization issue in the Bolt protocol. Used by {@link Neo4jError#code}.
 * @type {string}
 */
declare const PROTOCOL_ERROR: string;
/**
 * Error code representing an no classified error. Used by {@link Neo4jError#code}.
 * @type {string}
 */
declare const NOT_AVAILABLE: string;
/**
 * Possible error codes in the {@link Neo4jError}
 */
type Neo4jErrorCode = typeof SERVICE_UNAVAILABLE | typeof SESSION_EXPIRED | typeof PROTOCOL_ERROR | typeof NOT_AVAILABLE;
/**
 * Class for nested errors, to be used as causes in {@link Neo4jError}
 */
declare class GQLError extends Error {
    gqlStatus: string;
    gqlStatusDescription: string;
    diagnosticRecord: DiagnosticRecord | undefined;
    classification: ErrorClassification;
    rawClassification?: string;
    cause?: Error;
    __proto__: GQLError;
    /**
     * @constructor
     * @param {string} message - the error message
     * @param {string} gqlStatus - the GQL status code of the error
     * @param {string} gqlStatusDescription - the GQL status description of the error
     * @param {ErrorDiagnosticRecord} diagnosticRecord - the error diagnostic record
     * @param {Error} cause - Optional nested error, the cause of the error
     */
    constructor(message: string, gqlStatus: string, gqlStatusDescription: string, diagnosticRecord?: DiagnosticRecord, cause?: Error);
    /**
     * Returns whether a given GqlStatus code can be found in the cause chain of the error (including the error itself).
     *
     * @param {string} gqlStatus the GqlStatus code to find
     * @returns {boolean}
     */
    containsGqlCause(gqlStatus: string): boolean;
    /**
     * Returns the first error in the cause chain (including the error itself) with a given GqlStatus code.
     * Returns undefined if the GqlStatus code is not present anywhere in the chain.
     *
     * @param {string} gqlStatus the GqlStatus code to find
     * @returns {GQLError | Neo4jError | undefined}
     */
    findByGqlStatus(gqlStatus: string): GQLError | Neo4jError | undefined;
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
 * Class for all errors thrown/returned by the driver.
 */
declare class Neo4jError extends GQLError {
    /**
     * Optional error code. Will be populated when error originates in the database.
     */
    code: string;
    /**
     * Whether the request that caused this error can be safely retried without duplicate commits on the server.
     * This does not apply when running auto-commit transactions using {@link Session#run}
     *
     * @deprecated members using the spelling 'retriable' will be removed in 7.0. Use {@link retryable} instead.
     */
    retriable: boolean;
    /**
     * Whether the request that caused this error can be safely retried without duplicate commits on the server.
     * This does not apply when running auto-commit transactions using {@link Session#run}
     */
    retryable: boolean;
    /**
     * @constructor
     * @param {string} message - the error message
     * @param {string} code - Optional error code. Will be populated when error originates in the database.
     * @param {string} gqlStatus - the GQL status code of the error
     * @param {string} gqlStatusDescription - the GQL status description of the error
     * @param {DiagnosticRecord} diagnosticRecord - the error diagnostic record
     * @param {Error} cause - Optional nested error, the cause of the error
     */
    constructor(message: string, code: Neo4jErrorCode, gqlStatus: string, gqlStatusDescription: string, diagnosticRecord?: DiagnosticRecord, cause?: Error);
    /**
     * Verifies if the given error is retriable.
     *
     * @deprecated members using the spelling 'retriable' will be removed in 7.0. Use {@link isRetryable} instead.
     * @param {object|undefined|null} error the error object
     * @returns {boolean} true if the error is retriable
     */
    static isRetriable(error?: any | null): boolean;
    /**
     * Verifies if the given error is retryable.
     *
     * @param {object|undefined|null} error the error object
     * @returns {boolean} true if the error is retryable
     */
    static isRetryable(error?: any | null): boolean;
}
/**
 * Create a new error from a message and optional data
 * @param message the error message
 * @param {Neo4jErrorCode} [code] the error code
 * @param {Neo4jError} [cause]
 * @param {String} [gqlStatus]
 * @param {String} [gqlStatusDescription]
 * @param {DiagnosticRecord} diagnosticRecord - the error message
 * @return {Neo4jError} an {@link Neo4jError}
 * @private
 */
declare function newError(message: string, code?: Neo4jErrorCode, cause?: Error, gqlStatus?: string, gqlStatusDescription?: string, diagnosticRecord?: DiagnosticRecord): Neo4jError;
/**
 * Create a new GQL error from a message and optional data
 * @param message the error message
 * @param {Neo4jError} [cause]
 * @param {String} [gqlStatus]
 * @param {String} [gqlStatusDescription]
 * @param {DiagnosticRecord} diagnosticRecord - the error message
 * @return {Neo4jError} an {@link Neo4jError}
 * @private
 */
declare function newGQLError(message: string, cause?: Error, gqlStatus?: string, gqlStatusDescription?: string, diagnosticRecord?: DiagnosticRecord): GQLError;
/**
 * Verifies if the given error is retriable.
 *
 * @deprecated members using the spelling 'retriable' will be removed in 7.0. Use {@link isRetryableError} instead.
 * @public
 * @param {object|undefined|null} error the error object
 * @returns {boolean} true if the error is retriable
 */
declare const isRetriableError: typeof Neo4jError.isRetriable;
/**
 * Verifies if the given error is retryable.
 *
 * @public
 * @param {object|undefined|null} error the error object
 * @returns {boolean} true if the error is retryable
 */
declare const isRetryableError: typeof Neo4jError.isRetryable;
export { newError, newGQLError, isRetriableError, isRetryableError, Neo4jError, GQLError, SERVICE_UNAVAILABLE, SESSION_EXPIRED, PROTOCOL_ERROR };
