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
export type VectorType = 'INT8' | 'INT16' | 'INT32' | 'INT64' | 'FLOAT32' | 'FLOAT64';
/**
 * A wrapper class for JavaScript TypedArrays that makes the driver send them as a Vector type to the database.
 * @access public
 * @exports Vector
 * @class A Vector class that wraps a JavaScript TypedArray to enable writing/reading the Neo4j Vector type.
 * @param {Float32Array | Float64Array | Int8Array | Int16Array | Int32Array | BigInt64Array} typedArray The TypedArray to convert to a vector
 *
 * @constructor
 *
 */
export default class Vector<K extends Float32Array | Float64Array | Int8Array | Int16Array | Int32Array | BigInt64Array> {
    _typedArray: K;
    _type: VectorType;
    constructor(typedArray: K);
    /**
     * Converts the Vector back to a typedArray
     * @returns {Float32Array | Float64Array | Int8Array | Int16Array | Int32Array | BigInt64Array} - a TypedArray of the Vectors type.
     */
    asTypedArray(): K;
    /**
     * Gets the type of the Vector
     * @returns {VectorType} - The type of the vector, corresponding to the type of the wrapped TypedArray.
     */
    getType(): VectorType;
    toString(): string;
}
/**
 * Cast a TypedArray to a {@link Vector}
 * @access public
 * @param {Float32Array | Float64Array | Int8Array | Int16Array | Int32Array | BigInt64Array} typedArray - The value to use.
 * @return {Vector} - The Neo4j Vector ready to be used as a query parameter
 */
export declare function vector<K extends Float32Array | Float64Array | Int8Array | Int16Array | Int32Array | BigInt64Array>(typedArray: K): Vector<K>;
/**
 * Test if given object is an instance of the {@link Vector} class.
 * @param {Object} obj the object to test.
 * @return {boolean} `true` if given object is a {@link Vector}, `false` otherwise.
 */
export declare function isVector<K extends Float32Array | Float64Array | Int8Array | Int16Array | Int32Array | BigInt64Array>(obj: any): obj is Vector<K>;
