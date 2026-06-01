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
var __values = (this && this.__values) || function(o) {
    var s = typeof Symbol === "function" && Symbol.iterator, m = s && o[s], i = 0;
    if (m) return m.call(o);
    if (o && typeof o.length === "number") return {
        next: function () {
            if (o && i >= o.length) o = void 0;
            return { value: o && o[i++], done: !o };
        }
    };
    throw new TypeError(s ? "Object is not iterable." : "Symbol.iterator is not defined.");
};
var __read = (this && this.__read) || function (o, n) {
    var m = typeof Symbol === "function" && o[Symbol.iterator];
    if (!m) return o;
    var i = m.call(o), r, ar = [], e;
    try {
        while ((n === void 0 || n-- > 0) && !(r = i.next()).done) ar.push(r.value);
    }
    catch (error) { e = { error: error }; }
    finally {
        try {
            if (r && !r.done && (m = i["return"])) m.call(i);
        }
        finally { if (e) throw e.error; }
    }
    return ar;
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.RecordObjectMapping = exports.rulesRegistry = void 0;
exports.as = as;
exports.valueAs = valueAs;
var error_1 = require("./error");
var mapping_nameconventions_1 = require("./mapping.nameconventions");
exports.rulesRegistry = {};
var nameMapping = function (name) { return name; };
function register(constructor, rules) {
    exports.rulesRegistry[constructor.name] = rules;
}
function clearMappingRegistry() {
    exports.rulesRegistry = {};
}
function translateIdentifiers(translationFunction) {
    nameMapping = translationFunction;
}
function getCaseTranslator(databaseConvention, codeConvention) {
    var keys = Object.keys(mapping_nameconventions_1.nameConventions);
    if (!keys.includes(databaseConvention)) {
        throw (0, error_1.newError)("Naming convention ".concat(databaseConvention, " is not recognized, \n      please provide a recognized name convention or manually provide a translation function."));
    }
    if (!keys.includes(codeConvention)) {
        throw (0, error_1.newError)("Naming convention ".concat(codeConvention, " is not recognized, \n      please provide a recognized name convention or manually provide a translation function."));
    }
    // @ts-expect-error
    return function (name) { return mapping_nameconventions_1.nameConventions[databaseConvention].encode(mapping_nameconventions_1.nameConventions[codeConvention].tokenize(name)); };
}
exports.RecordObjectMapping = Object.freeze({
    /**
   * Clears all registered type mappings from the record object mapping registry.
   * @experimental Part of the Record Object Mapping preview feature
   */
    clearMappingRegistry: clearMappingRegistry,
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
    getCaseTranslator: getCaseTranslator,
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
    register: register,
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
    translateIdentifiers: translateIdentifiers
});
function as(gettable, constructorOrRules, rules) {
    var e_1, _a, e_2, _b;
    var GenericConstructor = typeof constructorOrRules === 'function' ? constructorOrRules : Object;
    var theRules = getRules(constructorOrRules, rules);
    var visitedKeys = [];
    var obj = new GenericConstructor();
    try {
        for (var _c = __values(Object.entries(theRules !== null && theRules !== void 0 ? theRules : {})), _d = _c.next(); !_d.done; _d = _c.next()) {
            var _e = __read(_d.value, 2), key = _e[0], rule = _e[1];
            visitedKeys.push(key);
            _apply(gettable, obj, key, rule);
        }
    }
    catch (e_1_1) { e_1 = { error: e_1_1 }; }
    finally {
        try {
            if (_d && !_d.done && (_a = _c.return)) _a.call(_c);
        }
        finally { if (e_1) throw e_1.error; }
    }
    try {
        for (var _f = __values(Object.getOwnPropertyNames(obj)), _g = _f.next(); !_g.done; _g = _f.next()) {
            var key = _g.value;
            if (!visitedKeys.includes(key)) {
                _apply(gettable, obj, key, theRules === null || theRules === void 0 ? void 0 : theRules[key]);
            }
        }
    }
    catch (e_2_1) { e_2 = { error: e_2_1 }; }
    finally {
        try {
            if (_g && !_g.done && (_b = _f.return)) _b.call(_f);
        }
        finally { if (e_2) throw e_2.error; }
    }
    return obj;
}
function _apply(gettable, obj, key, rule) {
    var _a;
    var mappedkey = nameMapping(key);
    var value = gettable.get((_a = rule === null || rule === void 0 ? void 0 : rule.from) !== null && _a !== void 0 ? _a : mappedkey);
    var field = "".concat(obj.constructor.name, "#").concat(key);
    var processedValue = valueAs(value, field, rule);
    // @ts-expect-error
    obj[key] = processedValue !== null && processedValue !== void 0 ? processedValue : obj[key];
}
function valueAs(value, field, rule) {
    if ((rule === null || rule === void 0 ? void 0 : rule.optional) === true && value == null) {
        return value;
    }
    if (typeof (rule === null || rule === void 0 ? void 0 : rule.validate) === 'function') {
        rule.validate(value, field);
    }
    return ((rule === null || rule === void 0 ? void 0 : rule.convert) != null) ? rule.convert(value, field) : value;
}
function getRules(constructorOrRules, rules) {
    var rulesDefined = typeof constructorOrRules === 'object' ? constructorOrRules : rules;
    if (rulesDefined != null) {
        return rulesDefined;
    }
    return typeof constructorOrRules !== 'object' ? exports.rulesRegistry[constructorOrRules.name] : undefined;
}
