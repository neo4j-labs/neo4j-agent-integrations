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
/**
 *
 * @access public
 * @class A class representing a protocol version the driver is using to communicate with the server.
 * @param {number} major the major version of the protocol.
 * @param {number} minor the minor version of the protocol.
 */
export declare class ProtocolVersion {
    private readonly major;
    private readonly minor;
    constructor(major: number, minor: number);
    /**
     *
     * @returns {number} The major version of the protocol
     */
    getMajor(): number;
    /**
     * @returns {number} The minor version of the protocol
     */
    getMinor(): number;
    /**
     *
     * @param {ProtocolVersion | {major: number, minor: number}} other the protocol version to compare to
     * @returns {boolean} If this version semantically smaller than the other version.
     */
    isLessThan(other: ProtocolVersion): boolean;
    /**
     *
     * @param {ProtocolVersion | {major: number, minor: number}} other the protocol version to compare to
     * @returns {boolean} If this version is semantically larger than the other version.
     */
    isGreaterThan(other: ProtocolVersion): boolean;
    /**
     *
     * @param {ProtocolVersion | {major: number, minor: number}} other the protocol version to compare to
     * @returns {boolean} if this version is semantically larger or equal to the other version.
     */
    isGreaterOrEqualTo(other: ProtocolVersion): boolean;
    /**
     *
     * @param {ProtocolVersion | {major: number, minor: number}} other the protocol version to compare to
     * @returns {boolean} if this version is semantically smaller or equal to the other version.
     */
    isLessOrEqualTo(other: ProtocolVersion): boolean;
    /**
     *
     * @param {ProtocolVersion | {major: number, minor: number}} other the protocol version to compare to
     * @returns {boolean} If this version is the equal to the other version.
     */
    isEqualTo(other: ProtocolVersion): boolean;
    toString(): string;
}
