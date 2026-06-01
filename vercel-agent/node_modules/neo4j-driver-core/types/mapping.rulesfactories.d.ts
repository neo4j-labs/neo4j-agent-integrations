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
import { Rule } from './mapping.highlevel';
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
export declare const rule: Readonly<{
    /**
     * Create a {@link Rule} that validates the value is a Boolean.
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asBoolean(rule?: Rule): Rule;
    /**
     * Create a {@link Rule} that validates the value is a String.
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asString(rule?: Rule): Rule;
    /**
     * Create a {@link Rule} that validates the value is a {@link Number}.
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule & { acceptBigInt?: boolean }} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asNumber(rule?: Rule & {
        acceptBigInt?: boolean;
    }): Rule;
    /**
     * Create a {@link Rule} that validates the value is a {@link BigInt}.
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule & { acceptNumber?: boolean }} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asBigInt(rule?: Rule & {
        acceptNumber?: boolean;
    }): Rule;
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
    asNode(rule?: Rule): Rule;
    /**
     * Create a {@link Rule} that validates the value is a {@link Relationship}.
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule.
     * @returns {Rule} A new rule for the value
     */
    asRelationship(rule?: Rule): Rule;
    /**
     * Create a {@link Rule} that validates the value is an {@link UnboundRelationship}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asUnboundRelationship(rule?: Rule): Rule;
    /**
     * Create a {@link Rule} that validates the value is a {@link Path}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asPath(rule?: Rule): Rule;
    /**
     * Create a {@link Rule} that validates the value is a {@link Point}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asPoint(rule?: Rule): Rule;
    /**
     * Create a {@link Rule} that validates the value is a {@link Duration}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asDuration(rule?: Rule & {
        stringify?: boolean;
    }): Rule;
    /**
     * Create a {@link Rule} that validates the value is a {@link LocalTime}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asLocalTime(rule?: Rule & {
        stringify?: boolean;
    }): Rule;
    /**
     * Create a {@link Rule} that validates the value is a {@link Time}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asTime(rule?: Rule & {
        stringify?: boolean;
    }): Rule;
    /**
     * Create a {@link Rule} that validates the value is a {@link Date}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asDate(rule?: Rule & {
        stringify?: boolean;
        toStandardDate?: boolean;
    }): Rule;
    /**
     * Create a {@link Rule} that validates the value is a {@link LocalDateTime}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asLocalDateTime(rule?: Rule & {
        stringify?: boolean;
        toStandardDate?: boolean;
    }): Rule;
    /**
     * Create a {@link Rule} that validates the value is a {@link DateTime}
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asDateTime(rule?: Rule & {
        stringify?: boolean;
        toStandardDate?: boolean;
    }): Rule;
    /**
     * Create a {@link Rule} that validates the value is a List. Optionally taking a rule for hydrating the contained values.
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule & { apply?: Rule }} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asList(rule?: Rule & {
        apply?: Rule;
    }): Rule;
    /**
     * Create a {@link Rule} that validates the value is a Vector.
     *
     * @experimental Part of the Record Object Mapping preview feature
     * @param {Rule & { asTypedList?: boolean }} rule Configurations for the rule
     * @returns {Rule} A new rule for the value
     */
    asVector(rule?: Rule & {
        asTypedList?: boolean;
    }): Rule;
}>;
