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
/**
 * constructor function of any class
 */
export type GenericConstructor<T extends {}> = new (...args: any[]) => T;
export interface Rule {
    optional?: boolean;
    from?: string;
    convert?: (recordValue: any, field: string) => any;
    validate?: (recordValue: any, field: string) => void;
}
export type Rules = Record<string, Rule>;
export declare let rulesRegistry: Record<string, Rules>;
declare function register<T extends {} = Object>(constructor: GenericConstructor<T>, rules: Rules): void;
declare function clearMappingRegistry(): void;
declare function translateIdentifiers(translationFunction: (name: string) => string): void;
declare function getCaseTranslator(databaseConvention: string, codeConvention: string): ((name: string) => string);
export declare const RecordObjectMapping: Readonly<{
    /**
   * Clears all registered type mappings from the record object mapping registry.
   * @experimental Part of the Record Object Mapping preview feature
   */
    clearMappingRegistry: typeof clearMappingRegistry;
    /**
   * Creates a translation function from record key names to object property names, for use with the {@link translateIdentifiers} function
   *
   * Recognized naming conventions are "camelCase", "PascalCase", "snake_case", "kebab-case", "SCREAMING_SNAKE_CASE"
   *
   * @experimental Part of the Record Object Mapping preview feature
   * @param {string} databaseConvention The naming convention in use in database result Records
   * @param {string} codeConvention The naming convention in use in JavaScript object properties
   * @returns {function} translation function
   */
    getCaseTranslator: typeof getCaseTranslator;
    /**
   * Registers a set of {@link Rules} to be used by {@link hydrated} for the provided class when no other rules are specified. This registry exists in global memory, not the driver instance.
   *
   * @example
   * // The following code:
   * const summary = await driver.executeQuery('CREATE (p:Person{ name: $name }) RETURN p', { name: 'Person1'}, {
   *  resultTransformer: neo4j.resultTransformers.hydrated(Person, personClassRules)
   * })
   *
   * can instead be written:
   * neo4j.RecordObjectMapping.register(Person, personClassRules)
   *
   * const summary = await driver.executeQuery('CREATE (p:Person{ name: $name }) RETURN p', { name: 'Person1'}, {
   *  resultTransformer: neo4j.resultTransformers.hydrated(Person)
   * })
   *
   * @experimental Part of the Record Object Mapping preview feature
   * @param {GenericConstructor} constructor The constructor function of the class to set rules for
   * @param {Rules} rules The rules to set for the provided class
   */
    register: typeof register;
    /**
   * Sets a default name translation from record keys to object properties.
   * If providing a function, provide a function that maps FROM your object properties names TO record key names.
   *
   * The function getCaseTranslator can be used to provide a prewritten translation function between some common naming conventions.
   *
   * @example
   * //if the keys on records from the database are in ALLCAPS
   * RecordObjectMapping.translateIdentifiers((name) => name.toUpperCase())
   *
   * //if you utilize PacalCase in the database and camelCase in JavaScript code.
   * RecordObjectMapping.translateIdentifiers(mapping.getCaseTranslator("PascalCase", "camelCase"))
   *
   * //if a type has one odd mapping you can override the translation with the rule
   * const personRules = {
   *  firstName: neo4j.rule.asString(),
   *  bornAt: neo4j.rule.asNumber({ acceptBigInt: true, optional: true })
   *  weird_name-property: neo4j.rule.asString({from: 'homeTown'})
   * }
   * //These rules can then be used by providing them to a hydratedResultsMapper
   * record.as<Person>(personRules)
   * //or by registering them to the mapping registry
   * RecordObjectMapping.register(Person, personRules)
   *
   * @experimental Part of the Record Object Mapping preview feature
   * @param {function} translationFunction A function translating the names of your JS object property names to record key names
   */
    translateIdentifiers: typeof translateIdentifiers;
}>;
interface Gettable {
    get: <V>(key: string) => V;
}
export declare function as<T extends {} = Object>(gettable: Gettable, constructorOrRules: GenericConstructor<T> | Rules, rules?: Rules): T;
export declare function valueAs(value: unknown, field: string, rule?: Rule): unknown;
export {};
