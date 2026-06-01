import { Rule } from './mapping.highlevel';
/**
 * Class Decorator Factory that enables the Neo4j Driver to map result records to this class
 *
 * @returns {Function} Class Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
declare function mappedClass(): (_: any, context: any) => void;
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a boolean.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
declare function booleanProperty(config?: Rule): (_: any, context: any) => void;
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a string.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
declare function stringProperty(config?: Rule): (_: any, context: any) => void;
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a number.
 *
 * @param {Rule & { acceptBigInt?: boolean }} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
declare function numberProperty(config?: Rule & {
    acceptBigInt?: boolean;
}): (_: any, context: any) => void;
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a BigInt.
 *
 * @param {Rule & { acceptNumber?: boolean }} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
declare function bigIntProperty(config?: Rule & {
    acceptNumber?: boolean;
}): (_: any, context: any) => void;
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a Node.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
declare function nodeProperty(config?: Rule): (_: any, context: any) => void;
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a Relationship.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
declare function relationshipProperty(config?: Rule): (_: any, context: any) => void;
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a Path.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
declare function pathProperty(config?: Rule): (_: any, context: any) => void;
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a Point.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
declare function pointProperty(config?: Rule): (_: any, context: any) => void;
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a Duration.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
declare function durationProperty(config?: Rule & {
    stringify?: boolean;
}): (_: any, context: any) => void;
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a List
 *
 * @param {Rule & { apply?: Rule }} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
declare function listProperty(config?: Rule & {
    apply?: Rule;
}): (_: any, context: any) => void;
/**
 * Property Decorator Factory that enables the Neo4j Driver to map this property to a Vector
 *
 * @param {Rule & { asTypedList?: boolean }} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
declare function vectorProperty(config?: Rule & {
    asTypedList?: boolean;
}): (_: any, context: any) => void;
/**
 * Property Decorator Factory that sets this property to optional.
 * NOTE: Should be put above a type decorator.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
declare function optionalProperty(): (_: any, context: any) => void;
/**
 * Property Decorator Factory that sets a custom parameter name to map this property to.
 * NOTE: Should be put above a type decorator.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
declare function mapPropertyFromName(name: string): (_: any, context: any) => void;
/**
 * Property Decorator Factory that sets the Neo4j Driver to convert this property to another type.
 * NOTE: Should be put above a type decorator of type Node or Relationship.
 *
 * @param {Rule} config
 * @returns {Function} Property Decorator
 * @experimental Part of the Record Object Mapping preview feature
 */
declare function convertPropertyToType(type: any): (_: any, context: any) => void;
declare const forExport: {
    booleanProperty: typeof booleanProperty;
    stringProperty: typeof stringProperty;
    numberProperty: typeof numberProperty;
    bigIntProperty: typeof bigIntProperty;
    nodeProperty: typeof nodeProperty;
    relationshipProperty: typeof relationshipProperty;
    pathProperty: typeof pathProperty;
    pointProperty: typeof pointProperty;
    durationProperty: typeof durationProperty;
    listProperty: typeof listProperty;
    vectorProperty: typeof vectorProperty;
    optionalProperty: typeof optionalProperty;
    mapPropertyFromName: typeof mapPropertyFromName;
    convertPropertyToType: typeof convertPropertyToType;
    mappedClass: typeof mappedClass;
};
export default forExport;
