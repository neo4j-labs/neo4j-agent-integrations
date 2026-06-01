"use strict";
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
Object.defineProperty(exports, "__esModule", { value: true });
var mapping_highlevel_1 = require("./mapping.highlevel");
var mapping_rulesfactories_1 = require("./mapping.rulesfactories");
/**
 * Class Decorator Factory that enables the Neo4j Driver to map result records to this class
 *
 * @returns {Function} Class Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
function mappedClass() {
    return function (_, context) {
        mapping_highlevel_1.rulesRegistry[context.name] = context.metadata;
    };
}
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a boolean.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
function booleanProperty(config) {
    return function (_, context) {
        context.metadata[context.name] = mapping_rulesfactories_1.rule.asBoolean(config);
    };
}
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a string.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
function stringProperty(config) {
    return function (_, context) {
        context.metadata[context.name] = mapping_rulesfactories_1.rule.asString(config);
    };
}
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a number.
 *
 * @param {Rule & { acceptBigInt?: boolean }} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
function numberProperty(config) {
    return function (_, context) {
        context.metadata[context.name] = mapping_rulesfactories_1.rule.asNumber(config);
    };
}
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a BigInt.
 *
 * @param {Rule & { acceptNumber?: boolean }} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
function bigIntProperty(config) {
    return function (_, context) {
        context.metadata[context.name] = mapping_rulesfactories_1.rule.asBigInt(config);
    };
}
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a Node.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
function nodeProperty(config) {
    return function (_, context) {
        context.metadata[context.name] = mapping_rulesfactories_1.rule.asNode(config);
    };
}
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a Relationship.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
function relationshipProperty(config) {
    return function (_, context) {
        context.metadata[context.name] = mapping_rulesfactories_1.rule.asRelationship(config);
    };
}
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a Path.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
function pathProperty(config) {
    return function (_, context) {
        context.metadata[context.name] = mapping_rulesfactories_1.rule.asPath(config);
    };
}
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a Point.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
function pointProperty(config) {
    return function (_, context) {
        context.metadata[context.name] = mapping_rulesfactories_1.rule.asPoint(config);
    };
}
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a Duration.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
function durationProperty(config) {
    return function (_, context) {
        context.metadata[context.name] = mapping_rulesfactories_1.rule.asDuration(config);
    };
}
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a List
 *
 * @param {Rule & { apply?: Rule }} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
function listProperty(config) {
    return function (_, context) {
        context.metadata[context.name] = mapping_rulesfactories_1.rule.asList(__assign({ apply: __assign({}, context.metadata[context.name]) }, config));
    };
}
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a Vector
 *
 * @param {Rule & { asTypedList?: boolean }} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
function vectorProperty(config) {
    return function (_, context) {
        context.metadata[context.name] = mapping_rulesfactories_1.rule.asVector(config);
    };
}
/**
 * Property Decorator Factory that sets this property to optional.
 * NOTE: Should be put above a type decorator.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
function optionalProperty() {
    return function (_, context) {
        context.metadata[context.name] = __assign({ optional: true }, context.metadata[context.name]);
    };
}
/**
 * Property Decorator Factory that sets a custom parameter name to map this property to.
 * NOTE: Should be put above a type decorator.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
function mapPropertyFromName(name) {
    return function (_, context) {
        context.metadata[context.name] = __assign({ from: name }, context.metadata[context.name]);
    };
}
/**
 * Property Decorator Factory that sets the Neo4j Driver to convert this property to another type.
 * NOTE: Should be put above a type decorator of type Node or Relationship.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
function convertPropertyToType(type) {
    return function (_, context) {
        context.metadata[context.name] = __assign({ convert: function (node) { return node.as(type); } }, context.metadata[context.name]);
    };
}
var forExport = {
    booleanProperty: booleanProperty,
    stringProperty: stringProperty,
    numberProperty: numberProperty,
    bigIntProperty: bigIntProperty,
    nodeProperty: nodeProperty,
    relationshipProperty: relationshipProperty,
    pathProperty: pathProperty,
    pointProperty: pointProperty,
    durationProperty: durationProperty,
    listProperty: listProperty,
    vectorProperty: vectorProperty,
    optionalProperty: optionalProperty,
    mapPropertyFromName: mapPropertyFromName,
    convertPropertyToType: convertPropertyToType,
    mappedClass: mappedClass
};
exports.default = forExport;
