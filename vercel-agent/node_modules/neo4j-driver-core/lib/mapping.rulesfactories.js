"use strict";
/**
 * Copyright (c) "Neo4j"
 * Neo4j Sweden AB [http://neo4j.com]
 *
 * This file is part of Neo4j.
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
var __assign = (this && this.__assign) || function () {
    __assign = Object.assign || function(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
        }
        return t;
    };
    return __assign.apply(this, arguments);
};
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.rule = void 0;
var mapping_highlevel_1 = require("./mapping.highlevel");
var graph_types_1 = require("./graph-types");
var spatial_types_1 = require("./spatial-types");
var temporal_types_1 = require("./temporal-types");
var vector_1 = __importDefault(require("./vector"));
/**
 * @property {function(rule: ?Rule)} asString Create a {@link Rule} that validates the value is a String.
 *
 * @property {function(rule: ?Rule & { acceptBigInt?: boolean })} asNumber Create a {@link Rule} that validates the value is a Number.
 *
 * @property {function(rule: ?Rule & { acceptNumber?: boolean })} AsBigInt Create a {@link Rule} that validates the value is a BigInt.
 *
 * @property {function(rule: ?Rule)} asNode Create a {@link Rule} that validates the value is a {@link Node}.
 *
 * @property {function(rule: ?Rule)} asRelationship Create a {@link Rule} that validates the value is a {@link Relationship}.
 *
 * @property {function(rule: ?Rule)} asPath Create a {@link Rule} that validates the value is a {@link Path}.
 *
 * @property {function(rule: ?Rule & { stringify?: boolean })} asDuration Create a {@link Rule} that validates the value is a {@link Duration}.
 *
 * @property {function(rule: ?Rule & { stringify?: boolean })} asLocalTime Create a {@link Rule} that validates the value is a {@link LocalTime}.
 *
 * @property {function(rule: ?Rule & { stringify?: boolean })} asLocalDateTime Create a {@link Rule} that validates the value is a {@link LocalDateTime}.
 *
 * @property {function(rule: ?Rule & { stringify?: boolean })} asTime Create a {@link Rule} that validates the value is a {@link Time}.
 *
 * @property {function(rule: ?Rule & { stringify?: boolean })} asDateTime Create a {@link Rule} that validates the value is a {@link DateTime}.
 *
 * @property {function(rule: ?Rule & { stringify?: boolean })} asDate Create a {@link Rule} that validates the value is a {@link Date}.
 *
 * @property {function(rule: ?Rule)} asPoint Create a {@link Rule} that validates the value is a {@link Point}.
 *
 * @property {function(rule: ?Rule & { apply?: Rule })} asList Create a {@link Rule} that validates the value is a List.
 *
 * @property {function(rule: ?Rule & { asTypedList: boolean })} asVector Create a {@link Rule} that validates the value is a List.
 *
 * @experimental Part of the Record Object Mapping preview feature
 */
exports.rule = Object.freeze({
    /**
     * Create a {@link Rule} that validates the value is a Boolean.
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asBoolean: function (rule) {
        return __assign({ validate: function (value, field) {
                if (typeof value !== 'boolean') {
                    throw new TypeError("".concat(field, " should be a boolean but received ").concat(typeof value));
                }
            } }, rule);
    },
    /**
     * Create a {@link Rule} that validates the value is a String.
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asString: function (rule) {
        return __assign({ validate: function (value, field) {
                if (typeof value !== 'string') {
                    throw new TypeError("".concat(field, " should be a string but received ").concat(typeof value));
                }
            } }, rule);
    },
    /**
     * Create a {@link Rule} that validates the value is a {@link Number}.
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule & { acceptBigInt?: boolean }} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asNumber: function (rule) {
        return __assign({ validate: function (value, field) {
                if (typeof value === 'object' && value.low !== undefined && value.high !== undefined && Object.keys(value).length === 2) {
                    throw new TypeError('Number returned as Object. To use asNumber mapping, set disableLosslessIntegers or useBigInt in driver config object');
                }
                if (typeof value !== 'number' && ((rule === null || rule === void 0 ? void 0 : rule.acceptBigInt) !== true || typeof value !== 'bigint')) {
                    throw new TypeError("".concat(field, " should be a number but received ").concat(typeof value));
                }
            }, convert: function (value) {
                if (typeof value === 'bigint') {
                    return Number(value);
                }
                return value;
            } }, rule);
    },
    /**
     * Create a {@link Rule} that validates the value is a {@link BigInt}.
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule & { acceptNumber?: boolean }} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asBigInt: function (rule) {
        return __assign({ validate: function (value, field) {
                if (typeof value !== 'bigint' && ((rule === null || rule === void 0 ? void 0 : rule.acceptNumber) !== true || typeof value !== 'number')) {
                    throw new TypeError("".concat(field, " should be a bigint but received ").concat(typeof value));
                }
            }, convert: function (value) {
                if (typeof value === 'number') {
                    return BigInt(value);
                }
                return value;
            } }, rule);
    },
    /**
     * Create a {@link Rule} that validates the value is a {@link Node}.
     *
     * @example
     * const actingJobsRules: Rules = {
     *  // Converts the person node to a Person object in accordance with provided rules
     *  person: neo4j.rule.asNode({
     *    convert: (node: Node) => node.as(Person, personRules)
     *  }),
     *  // Returns the movie node as a Node
     *  movie: neo4j.rule.asNode({}),
     * }
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asNode: function (rule) {
        return __assign({ validate: function (value, field) {
                if (!(0, graph_types_1.isNode)(value)) {
                    throw new TypeError("".concat(field, " should be a Node but received ").concat(typeof value));
                }
            } }, rule);
    },
    /**
     * Create a {@link Rule} that validates the value is a {@link Relationship}.
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule.
     * @returns {Rule} A new rule for the value
     */
    asRelationship: function (rule) {
        return __assign({ validate: function (value, field) {
                if (!(0, graph_types_1.isRelationship)(value)) {
                    throw new TypeError("".concat(field, " should be a Relationship but received ").concat(typeof value));
                }
            } }, rule);
    },
    /**
     * Create a {@link Rule} that validates the value is an {@link UnboundRelationship}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asUnboundRelationship: function (rule) {
        return __assign({ validate: function (value, field) {
                if (!(0, graph_types_1.isUnboundRelationship)(value)) {
                    throw new TypeError("".concat(field, " should be a UnboundRelationship but received ").concat(typeof value));
                }
            } }, rule);
    },
    /**
     * Create a {@link Rule} that validates the value is a {@link Path}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asPath: function (rule) {
        return __assign({ validate: function (value, field) {
                if (!(0, graph_types_1.isPath)(value)) {
                    throw new TypeError("".concat(field, " should be a Path but received ").concat(typeof value));
                }
            } }, rule);
    },
    /**
     * Create a {@link Rule} that validates the value is a {@link Point}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asPoint: function (rule) {
        return __assign({ validate: function (value, field) {
                if (!(0, spatial_types_1.isPoint)(value)) {
                    throw new TypeError("".concat(field, " should be a Point but received ").concat(typeof value));
                }
            } }, rule);
    },
    /**
     * Create a {@link Rule} that validates the value is a {@link Duration}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asDuration: function (rule) {
        return __assign({ validate: function (value, field) {
                if (!(0, temporal_types_1.isDuration)(value)) {
                    throw new TypeError("".concat(field, " should be a Duration but received ").concat(typeof value));
                }
            }, convert: function (value) { return (rule === null || rule === void 0 ? void 0 : rule.stringify) === true ? value.toString() : value; } }, rule);
    },
    /**
     * Create a {@link Rule} that validates the value is a {@link LocalTime}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asLocalTime: function (rule) {
        return __assign({ validate: function (value, field) {
                if (!(0, temporal_types_1.isLocalTime)(value)) {
                    throw new TypeError("".concat(field, " should be a LocalTime but received ").concat(typeof value));
                }
            }, convert: function (value) { return (rule === null || rule === void 0 ? void 0 : rule.stringify) === true ? value.toString() : value; } }, rule);
    },
    /**
     * Create a {@link Rule} that validates the value is a {@link Time}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asTime: function (rule) {
        return __assign({ validate: function (value, field) {
                if (!(0, temporal_types_1.isTime)(value)) {
                    throw new TypeError("".concat(field, " should be a Time but received ").concat(typeof value));
                }
            }, convert: function (value) { return (rule === null || rule === void 0 ? void 0 : rule.stringify) === true ? value.toString() : value; } }, rule);
    },
    /**
     * Create a {@link Rule} that validates the value is a {@link Date}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asDate: function (rule) {
        return __assign({ validate: function (value, field) {
                if (!(0, temporal_types_1.isDate)(value)) {
                    throw new TypeError("".concat(field, " should be a Date but received ").concat(typeof value));
                }
            }, convert: function (value) { return convertStdDate(value, rule); } }, rule);
    },
    /**
     * Create a {@link Rule} that validates the value is a {@link LocalDateTime}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asLocalDateTime: function (rule) {
        return __assign({ validate: function (value, field) {
                if (!(0, temporal_types_1.isLocalDateTime)(value)) {
                    throw new TypeError("".concat(field, " should be a LocalDateTime but received ").concat(typeof value));
                }
            }, convert: function (value) { return convertStdDate(value, rule); } }, rule);
    },
    /**
     * Create a {@link Rule} that validates the value is a {@link DateTime}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asDateTime: function (rule) {
        return __assign({ validate: function (value, field) {
                if (!(0, temporal_types_1.isDateTime)(value)) {
                    throw new TypeError("".concat(field, " should be a DateTime but received ").concat(typeof value));
                }
            }, convert: function (value) { return convertStdDate(value, rule); } }, rule);
    },
    /**
     * Create a {@link Rule} that validates the value is a List. Optionally taking a rule for hydrating the contained values.
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule & { apply?: Rule }} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asList: function (rule) {
        return __assign({ validate: function (value, field) {
                if (!Array.isArray(value)) {
                    throw new TypeError("".concat(field, " should be a list but received ").concat(typeof value));
                }
            }, convert: function (list, field) {
                if ((rule === null || rule === void 0 ? void 0 : rule.apply) != null) {
                    return list.map(function (value, index) { return (0, mapping_highlevel_1.valueAs)(value, "".concat(field, "[").concat(index, "]"), rule.apply); });
                }
                return list;
            } }, rule);
    },
    /**
     * Create a {@link Rule} that validates the value is a Vector.
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule & { asTypedList?: boolean }} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asVector: function (rule) {
        return __assign({ validate: function (value, field) {
                if (!(value instanceof vector_1.default)) {
                    throw new TypeError("".concat(field, " should be a vector but received ").concat(typeof value));
                }
            }, convert: function (value) {
                if ((rule === null || rule === void 0 ? void 0 : rule.asTypedList) === true) {
                    return value._typedArray;
                }
                return value;
            } }, rule);
    }
});
function convertStdDate(value, rule) {
    if (rule != null) {
        if (rule.stringify === true) {
            return value.toString();
        }
        else if (rule.toStandardDate === true) {
            return value.toStandardDate();
        }
    }
    return value;
}
