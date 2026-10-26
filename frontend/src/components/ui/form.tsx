import type * as LabelPrimitive from "@radix-ui/react-label";
import { Slot } from "@radix-ui/react-slot";
import * as React from "react";
import {
  Controller,
  type ControllerProps,
  type FieldPath,
  type FieldValues,
  FormProvider,
  useFormContext,
} from "react-hook-form";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const Form = FormProvider;

type FormFieldContextValue<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
> = {
  name: TName;
};

const FormFieldContext = React.createContext<FormFieldContextValue>({} as FormFieldContextValue);

const FormField = <
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
>({
  ...props
}: ControllerProps<TFieldValues, TName>) => {
  return (
    <FormFieldContext value={{ name: props.name }}>
      <Controller {...props} />
    </FormFieldContext>
  );
};

const useFormField = () => {
  const fieldContext = React.use(FormFieldContext);
  const itemContext = React.use(FormItemContext);
  const { getFieldState, formState } = useFormContext();

  const fieldState = getFieldState(fieldContext.name, formState);

  if (!fieldContext) {
    throw new Error("useFormField should be used within <FormField>");
  }

  const { id } = itemContext;

  return {
    id,
    name: fieldContext.name,
    formItemId: `${id}-form-item`,
    formDescriptionId: `${id}-form-item-description`,
    formMessageId: `${id}-form-item-message`,
    ...fieldState,
  };
};

type FormItemContextValue = {
  id: string;
};

const FormItemContext = React.createContext<FormItemContextValue>({} as FormItemContextValue);

export function FormItem({
  className,
  ref,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { ref?: React.Ref<HTMLDivElement> }) {
  const id = React.useId();

  return (
    <FormItemContext value={{ id }}>
      <div ref={ref} className={cn("space-y-2", className)} {...props} />
    </FormItemContext>
  );
}

export function FormLabel({
  className,
  ref,
  ...props
}: React.ComponentProps<typeof LabelPrimitive.Root> & {
  ref?: React.Ref<HTMLLabelElement>;
}) {
  const { error, formItemId } = useFormField();

  return (
    <Label
      ref={ref}
      className={cn(error && "text-destructive", className)}
      htmlFor={formItemId}
      {...props}
    />
  );
}

export function FormControl({
  ref,
  ...props
}: React.ComponentProps<typeof Slot> & {
  ref?: React.Ref<React.ElementRef<typeof Slot>>;
}) {
  const { error, formItemId, formDescriptionId, formMessageId } = useFormField();

  return (
    <Slot
      ref={ref}
      id={formItemId}
      aria-describedby={!error ? `${formDescriptionId}` : `${formDescriptionId} ${formMessageId}`}
      aria-invalid={!!error}
      {...props}
    />
  );
}

export function FormDescription({
  className,
  ref,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement> & {
  ref?: React.Ref<HTMLParagraphElement>;
}) {
  const { formDescriptionId } = useFormField();

  return (
    <p
      ref={ref}
      id={formDescriptionId}
      className={cn("text-xs text-muted-foreground", className)}
      {...props}
    />
  );
}

export function FormMessage({
  className,
  children,
  ref,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement> & {
  ref?: React.Ref<HTMLParagraphElement>;
}) {
  const { error, formMessageId } = useFormField();
  const body = error ? String(error.message ?? "") : children;

  if (!body) {
    return null;
  }

  return (
    <p
      ref={ref}
      id={formMessageId}
      role="alert"
      className={cn("text-xs font-medium text-destructive", className)}
      {...props}
    >
      {body}
    </p>
  );
}

export { Form, FormField, useFormField };
